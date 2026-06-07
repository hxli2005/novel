"""FastAPI app: upload a novel, run the pipeline (async), stream live progress.

Runs execute in a thread pool; each emits per-stage events into an in-memory
RunState that the SSE endpoint streams to the browser. The browser watches the
six-stage timeline and navigates to the result page on completion.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from novel_to_screenplay.exporters import write_docx, write_fountain
from novel_to_screenplay.pipeline.chapter_parser import ChapterParseError
from novel_to_screenplay.pipeline.screenplay_generator import ScreenplayGenerationOptions
from novel_to_screenplay.pipeline.screenplay_validator import load_yaml_document
from novel_to_screenplay.providers import ProviderError, build_provider, get_provider_statuses
from novel_to_screenplay.runner import run_pipeline
from novel_to_screenplay.workspace import (
    build_workspace_layout,
    find_staged_source_file,
    initialize_workspace,
    stage_source_file,
)

BASE_DIR = Path(__file__).resolve().parent
# Anchor to the repo root (src/novel_to_screenplay/web/app.py -> parents[3]) so
# `serve` works regardless of the launch directory.
REPO_ROOT = BASE_DIR.parents[2]
RUNS_DIR = REPO_ROOT / "runs" / "web"
SCHEMA_PATH = REPO_ROOT / "schemas" / "screenplay.schema.json"
SAMPLE_NOVEL = REPO_ROOT / "examples" / "novels" / "three_chapters.txt"
SUPPORTED_SUFFIXES = {".txt", ".md"}
RUN_ID_RE = re.compile(r"[0-9a-f]{12}")
MAX_TRACKED_RUNS = 32

TARGET_FORMATS = [
    "screenplay",
    "tv_episode",
    "web_series_episode",
    "microdrama_episode",
    "stage_play",
]
FIDELITIES = ["faithful", "balanced", "loose"]
PACINGS = ["slow_burn", "balanced", "compressed", "fast"]

app = FastAPI(title="Inkdraft 墨稿")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_executor = ThreadPoolExecutor(max_workers=4)
_runs_lock = threading.Lock()


@dataclass
class RunState:
    """In-memory progress for one run; events are streamed over SSE."""

    status: str = "running"  # running | done | error
    error: str | None = None
    events: list[dict] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


_runs: dict[str, RunState] = {}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return _render_index(request, error=None)


def _render_index(request: Request, error: str | None, status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "providers": get_provider_statuses(),
            "target_formats": TARGET_FORMATS,
            "fidelities": FIDELITIES,
            "pacings": PACINGS,
            "error": error,
        },
        status_code=status_code,
    )


def _render_index_error(request: Request, message: str) -> HTMLResponse:
    return _render_index(request, error=message, status_code=400)


@app.post("/runs", response_model=None)
async def create_run(
    request: Request,
    file: UploadFile | None = File(default=None),
    use_sample: str = Form(default=""),
    provider: str = Form(default="mock"),
    title: str = Form(default="剧本初稿"),
    author: str = Form(default="待填写"),
    target_format: str = Form(default="screenplay"),
    fidelity: str = Form(default="balanced"),
    pacing: str = Form(default="compressed"),
    runtime: int = Form(default=8),
    chapter_start: int = Form(default=1),
    chapter_end: str = Form(default=""),
) -> HTMLResponse | RedirectResponse:
    run_id = uuid.uuid4().hex[:12]
    layout = initialize_workspace(RUNS_DIR / run_id)

    if use_sample:
        source_path = SAMPLE_NOVEL
    elif file is not None and file.filename:
        suffix = Path(file.filename).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            return _render_index_error(request, "只支持 .txt / .md 文件。")
        source_path = layout.root / f"upload{suffix}"
        source_path.write_bytes(await file.read())
    else:
        return _render_index_error(request, "请上传一个 .txt / .md 小说文件，或使用内置示例。")

    staged_path = stage_source_file(source_path, layout)
    try:
        provider_obj = build_provider(provider)
    except ProviderError as exc:
        return _render_index_error(request, f"模型不可用：{exc}。可改用离线 mock。")

    _start_run(
        run_id,
        layout,
        staged_path,
        provider_obj,
        {
            "title": title,
            "author": author,
            "target_format": target_format,
            "fidelity": fidelity,
            "pacing": pacing,
            "runtime": runtime,
            "provider": provider,
            "chapter_start": chapter_start,
            "chapter_end": _parse_optional_int(chapter_end),
        },
    )
    return RedirectResponse(f"/runs/{run_id}/running", status_code=303)


@app.post("/runs/{run_id}/rerun", response_model=None)
def rerun(
    request: Request,
    run_id: str,
    chapter_start: int = Form(default=1),
    chapter_end: str = Form(default=""),
) -> HTMLResponse | RedirectResponse:
    if _run_output_dir(run_id) is None:
        return _render_index_error(request, "找不到该剧本，请重新生成。")
    layout = build_workspace_layout(RUNS_DIR / run_id)
    try:
        staged_path = find_staged_source_file(layout)
    except FileNotFoundError:
        return _render_index_error(request, "原文已不可用，请重新上传生成。")
    meta = _read_run_meta(layout)
    try:
        provider_obj = build_provider(meta.get("provider", "mock"))
    except ProviderError as exc:
        return _render_index_error(request, f"模型不可用：{exc}。可改用离线 mock。")

    _start_run(
        run_id,
        layout,
        staged_path,
        provider_obj,
        {
            "title": meta.get("title", "剧本初稿"),
            "author": meta.get("author", "待填写"),
            "target_format": meta.get("target_format", "screenplay"),
            "fidelity": meta.get("fidelity", "balanced"),
            "pacing": meta.get("pacing", "compressed"),
            "runtime": meta.get("runtime", 8),
            "provider": meta.get("provider", "mock"),
            "chapter_start": chapter_start,
            "chapter_end": _parse_optional_int(chapter_end),
        },
    )
    return RedirectResponse(f"/runs/{run_id}/running", status_code=303)


@app.get("/runs/{run_id}/running", response_class=HTMLResponse)
def running(request: Request, run_id: str) -> HTMLResponse:
    return templates.TemplateResponse(request, "running.html", {"run_id": run_id})


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@app.get("/runs/{run_id}/events")
async def events(run_id: str) -> Response:
    state = _runs.get(run_id)
    if state is None:
        # The run is no longer tracked (server restart / eviction / stale link).
        # Emit one terminal frame so the client navigates to the result page
        # instead of EventSource retrying the 404 forever.
        async def gone() -> Any:
            yield f"data: {json.dumps({'stage': 'complete', 'status': 'done'})}\n\n"

        return StreamingResponse(gone(), media_type="text/event-stream", headers=_SSE_HEADERS)

    async def stream() -> Any:
        sent = 0
        while True:
            with state.lock:
                pending = state.events[sent:]
                sent += len(pending)
                status = state.status
            for event in pending:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if status in {"done", "error"}:
                break
            await asyncio.sleep(0.15)

    return StreamingResponse(stream(), media_type="text/event-stream", headers=_SSE_HEADERS)


@app.get("/runs/{run_id}", response_model=None)
def view_run(request: Request, run_id: str) -> HTMLResponse | RedirectResponse:
    state = _runs.get(run_id)
    # While a run (or rerun) is in flight, always show the running page rather
    # than a possibly-stale earlier result still on disk.
    if state is not None and state.status == "running":
        return RedirectResponse(f"/runs/{run_id}/running", status_code=303)
    document = _load_run(run_id)
    if document is None:
        if state is not None and state.status == "error" and state.error:
            return _render_index_error(request, state.error)
        return _render_index_error(request, "找不到该剧本，请重新生成。")
    layout = build_workspace_layout(RUNS_DIR / run_id)
    return templates.TemplateResponse(
        request,
        "result.html",
        {"run_id": run_id, "doc": document, "meta": _read_run_meta(layout)},
    )


@app.get("/runs/{run_id}/download/{fmt}", response_model=None)
def download(run_id: str, fmt: str) -> FileResponse | HTMLResponse:
    output_dir = _run_output_dir(run_id)
    if output_dir is None:
        return HTMLResponse("not found", status_code=404)
    yaml_path = output_dir / "screenplay.yaml"
    if not yaml_path.is_file():
        return HTMLResponse("not found", status_code=404)
    if fmt == "yaml":
        return FileResponse(yaml_path, filename="screenplay.yaml")
    document = load_yaml_document(yaml_path)
    if not isinstance(document, dict):
        return HTMLResponse("invalid screenplay", status_code=400)
    if fmt == "fountain":
        path = output_dir / "screenplay.fountain"
        write_fountain(document, path)
        return FileResponse(path, filename="screenplay.fountain")
    if fmt == "docx":
        path = output_dir / "screenplay.docx"
        write_docx(document, path)
        return FileResponse(path, filename="screenplay.docx")
    return HTMLResponse("unknown format", status_code=404)


def _start_run(
    run_id: str,
    layout: Any,
    staged_path: Path,
    provider_obj: Any,
    params: dict[str, Any],
) -> None:
    state = RunState()
    with _runs_lock:
        _runs[run_id] = state
        # Evict only terminal runs beyond the cap; never drop an in-flight run
        # (that would 404 its live SSE clients).
        evictable = [rid for rid, st in _runs.items() if st.status != "running"]
        while len(_runs) > MAX_TRACKED_RUNS and evictable:
            _runs.pop(evictable.pop(0), None)
    # Pass the RunState directly so the worker never re-looks-it-up (avoids a
    # KeyError if this run is evicted before the worker starts).
    _executor.submit(_run_worker, state, layout, staged_path, provider_obj, params)


def _run_worker(
    state: RunState,
    layout: Any,
    staged_path: Path,
    provider_obj: Any,
    params: dict[str, Any],
) -> None:
    current = {"stage": "parse"}

    def on_event(event: dict) -> None:
        if event.get("status") == "start":
            current["stage"] = event.get("stage", current["stage"])
        with state.lock:
            state.events.append(event)

    try:
        options = ScreenplayGenerationOptions(
            title=params["title"] or "剧本初稿",
            author=params["author"] or "待填写",
            target_format=params["target_format"],
            fidelity=params["fidelity"],
            pacing=params["pacing"],
            target_runtime_min=int(params["runtime"]),
        )
        result = run_pipeline(
            staged_path,
            layout,
            provider_obj,
            options,
            outline_adaptation={
                "target_format": params["target_format"],
                "pacing": params["pacing"],
            },
            schema=SCHEMA_PATH,
            on_event=on_event,
            chapter_start=params["chapter_start"],
            chapter_end=params["chapter_end"],
        )
        _write_run_meta(
            layout,
            {
                "total_chapters": result.total_chapters,
                "chapter_start": result.chapter_start,
                "chapter_end": result.chapter_end,
                "title": params["title"],
                "author": params["author"],
                "target_format": params["target_format"],
                "fidelity": params["fidelity"],
                "pacing": params["pacing"],
                "runtime": int(params["runtime"]),
                "provider": params["provider"],
            },
        )
        with state.lock:
            state.events.append({"stage": "complete", "status": "done"})
            state.status = "done"
    except ChapterParseError as exc:
        if "章" in str(exc):
            message = str(exc)
        else:
            message = "未能识别到至少 3 个章节，请检查章节标记（如“第一章”）。"
        _fail_run(state, "parse", message)
    except ProviderError as exc:
        _fail_run(state, current["stage"], f"模型调用失败：{exc}。可改用离线 mock 重试。")
    except Exception as exc:  # noqa: BLE001 - never surface a raw 500 to the user
        _fail_run(state, current["stage"], f"转换失败：{exc}")
    finally:
        # Safety net: guarantee a terminal status so SSE clients never hang,
        # even if an error escaped the handlers above.
        with state.lock:
            if state.status == "running":
                state.events.append(
                    {"stage": current["stage"], "status": "error", "message": "转换失败，请重试。"}
                )
                state.status = "error"


def _fail_run(state: RunState, stage: str, message: str) -> None:
    with state.lock:
        state.error = message
        state.events.append({"stage": stage, "status": "error", "message": message})
        state.status = "error"


def _parse_optional_int(value: str) -> int | None:
    value = value.strip()
    return int(value) if value.isdigit() else None


def _write_run_meta(layout: Any, meta: dict) -> None:
    (layout.root / "run.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _read_run_meta(layout: Any) -> dict:
    path = layout.root / "run.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _run_output_dir(run_id: str) -> Path | None:
    """Resolve a run's output dir, rejecting any run_id that is not a run token.

    Validating against the generated token shape (12 hex chars) prevents path
    traversal (e.g. '..') from escaping the runs directory.
    """

    if not RUN_ID_RE.fullmatch(run_id):
        return None
    return build_workspace_layout(RUNS_DIR / run_id).output_dir


def _load_run(run_id: str) -> dict | None:
    output_dir = _run_output_dir(run_id)
    if output_dir is None:
        return None
    yaml_path = output_dir / "screenplay.yaml"
    if not yaml_path.is_file():
        return None
    document = load_yaml_document(yaml_path)
    return document if isinstance(document, dict) else None
