"""FastAPI app: upload a novel, run the pipeline, read and export the screenplay.

This is the synchronous vertical slice (upload -> run -> result + downloads).
Live per-stage progress (SSE) and richer interactions layer on in later steps.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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
    initialize_workspace,
    stage_source_file,
)

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = Path("runs/web")
SCHEMA_PATH = Path("schemas/screenplay.schema.json")
SAMPLE_NOVEL = Path("examples/novels/three_chapters.txt")
SUPPORTED_SUFFIXES = {".txt", ".md"}

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


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "providers": get_provider_statuses(),
            "target_formats": TARGET_FORMATS,
            "fidelities": FIDELITIES,
            "pacings": PACINGS,
            "error": None,
        },
    )


def _render_index_error(request: Request, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "providers": get_provider_statuses(),
            "target_formats": TARGET_FORMATS,
            "fidelities": FIDELITIES,
            "pacings": PACINGS,
            "error": message,
        },
        status_code=400,
    )


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
    options = ScreenplayGenerationOptions(
        title=title or "剧本初稿",
        author=author or "待填写",
        target_format=target_format,
        fidelity=fidelity,
        pacing=pacing,
        target_runtime_min=int(runtime),
    )
    try:
        provider_obj = build_provider(provider)
        run_pipeline(
            staged_path,
            layout,
            provider_obj,
            options,
            outline_adaptation={"target_format": target_format, "pacing": pacing},
            schema=SCHEMA_PATH,
        )
    except ChapterParseError:
        message = "未能识别到至少 3 个章节，请检查章节标记（如“第一章”）。"
        return _render_index_error(request, message)
    except ProviderError as exc:
        return _render_index_error(request, f"模型调用失败：{exc}。可改用离线 mock 重试。")

    return RedirectResponse(f"/runs/{run_id}", status_code=303)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def view_run(request: Request, run_id: str) -> HTMLResponse:
    document = _load_run(run_id)
    if document is None:
        return _render_index_error(request, "找不到该剧本，请重新生成。")
    return templates.TemplateResponse(
        request,
        "result.html",
        {"run_id": run_id, "doc": document},
    )


@app.get("/runs/{run_id}/download/{fmt}", response_model=None)
def download(run_id: str, fmt: str) -> FileResponse | HTMLResponse:
    output_dir = build_workspace_layout(RUNS_DIR / run_id).output_dir
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


def _load_run(run_id: str) -> dict | None:
    yaml_path = build_workspace_layout(RUNS_DIR / run_id).output_dir / "screenplay.yaml"
    if not yaml_path.is_file():
        return None
    document = load_yaml_document(yaml_path)
    return document if isinstance(document, dict) else None
