import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from novel_to_screenplay.providers import ProviderCompletion
from novel_to_screenplay.web.app import app

client = TestClient(app)


def _start_run(**post) -> str:  # type: ignore[no-untyped-def]
    """POST /runs (follows the 303 to the running page); return the run_id."""
    response = client.post("/runs", **post)
    assert response.status_code == 200  # the running page
    # final URL is /runs/{id}/running
    return response.url.path.split("/")[2]


def _await_run(run_id: str) -> None:
    """Drain the SSE stream, which closes once the run reaches a terminal state."""
    with client.stream("GET", f"/runs/{run_id}/events") as stream:
        for _ in stream.iter_lines():
            pass


def _run(**post) -> str:  # type: ignore[no-untyped-def]
    run_id = _start_run(**post)
    _await_run(run_id)
    return run_id


def _multi_chapter_novel(count: int) -> bytes:
    return "\n\n".join(f"第{i}章 标题{i}\n内容{i}。" for i in range(1, count + 1)).encode("utf-8")


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_renders_upload_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "墨稿" in response.text
    assert "开始改编" in response.text


def test_running_page_renders_timeline() -> None:
    run_id = _start_run(data={"use_sample": "1", "provider": "mock"})
    page = client.get(f"/runs/{run_id}/running")
    assert page.status_code == 200
    assert "正在改编" in page.text
    assert "逐场扩写" in page.text  # the draft stage node
    assert f"/runs/{run_id}/cancel" in page.text  # the cancel form posts here
    _await_run(run_id)


def test_run_sample_end_to_end_and_downloads() -> None:
    run_id = _run(data={"use_sample": "1", "provider": "mock"})
    result = client.get(f"/runs/{run_id}")
    assert result.status_code == 200
    assert "质量报告" in result.text
    assert "林青" in result.text  # extracted character

    for fmt in ["yaml", "fountain", "docx", "fdx"]:
        download = client.get(f"/runs/{run_id}/download/{fmt}")
        assert download.status_code == 200, fmt
        assert download.content, fmt

    # The Final Draft export must be downloadable and well-formed XML, and the
    # result page must offer it.
    import xml.etree.ElementTree as ET

    fdx = client.get(f"/runs/{run_id}/download/fdx")
    assert ET.fromstring(fdx.content).tag == "FinalDraft"
    assert "/runs/" in result.text and "download/fdx" in result.text


def test_result_page_groups_quality_and_lists_locations() -> None:
    run_id = _run(data={"use_sample": "1", "provider": "mock"})
    result = client.get(f"/runs/{run_id}")
    text = result.text
    # Drawer tabs + locations panel.
    assert "人物 · 地点" in text
    assert "地点" in text
    # The pipeline ran the deterministic checks, shown under the structural group
    # with a Chinese gloss (not the raw code).
    assert "结构检查" in text
    assert "人物无台词" in text


class _StoryReviewProvider:
    name = "fake"
    model = "fake"

    def complete(self, messages, *, temperature=0.2, max_tokens=2048):  # type: ignore[no-untyped-def]
        del messages, temperature, max_tokens
        payload = [
            {"code": "FORESHADOW_UNRESOLVED", "message": "铜钥匙未回收。", "scene_id": "sc_001"}
        ]
        return ProviderCompletion(
            text=json.dumps(payload, ensure_ascii=False), provider="fake", model="fake", usage={}
        )


def test_review_button_disabled_for_mock_then_adds_story_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = _run(data={"use_sample": "1", "provider": "mock"})
    # A mock run can't do the LLM review, so the button is disabled.
    assert "需 DeepSeek 引擎" in client.get(f"/runs/{run_id}").text

    # With an LLM provider, the review populates the 故事级复审 group.
    monkeypatch.setattr(
        "novel_to_screenplay.web.app.build_provider", lambda *a, **k: _StoryReviewProvider()
    )
    response = client.post(f"/runs/{run_id}/review")
    assert response.status_code == 200  # followed redirect to the result page
    assert "故事级复审" in response.text
    assert "伏笔未回收" in response.text  # the Chinese gloss for FORESHADOW_UNRESOLVED


def test_cancel_aborts_in_flight_run(monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()

    def fake_run_pipeline(*args, on_event=None, **kwargs):  # type: ignore[no-untyped-def]
        # Emit one event, then spin emitting more until the cancel flag makes
        # on_event raise RunCancelled (cooperative cancellation).
        on_event({"stage": "parse", "status": "start"})
        started.set()
        for _ in range(2000):
            on_event({"stage": "draft", "status": "progress", "index": 1, "total": 1})
            time.sleep(0.005)
        raise AssertionError("run was not cancelled")  # pragma: no cover

    monkeypatch.setattr("novel_to_screenplay.web.app.run_pipeline", fake_run_pipeline)

    run_id = _start_run(data={"use_sample": "1", "provider": "mock"})
    assert started.wait(timeout=5)  # the worker is alive and looping
    assert client.post(f"/runs/{run_id}/cancel").status_code == 200  # 303 -> "/"

    # The SSE stream must terminate with a cancelled frame (not hang or error).
    frames = []
    with client.stream("GET", f"/runs/{run_id}/events") as stream:
        for line in stream.iter_lines():
            if line.startswith("data:"):
                frames.append(line)
    assert any('"cancelled"' in f for f in frames)


def test_history_lists_completed_runs_newest_first() -> None:
    older = _run(data={"use_sample": "1", "provider": "mock", "title": "历史较早"})
    newer = _run(data={"use_sample": "1", "provider": "mock", "title": "历史较新"})

    page = client.get("/history")
    assert page.status_code == 200
    assert "历史较早" in page.text and "历史较新" in page.text
    assert f"/runs/{older}" in page.text and f"/runs/{newer}" in page.text
    # The most recently generated run is listed first.
    assert page.text.index(f"/runs/{newer}") < page.text.index(f"/runs/{older}")


def test_header_links_to_history() -> None:
    assert 'href="/history"' in client.get("/").text


def test_run_accepts_gbk_encoded_upload() -> None:
    # Chinese novels are frequently GBK-encoded; this must not return 500.
    text = "第一章 起\n中文内容。\n\n第二章 承\n更多内容。\n\n第三章 合\n结尾。\n"
    run_id = _run(
        data={"provider": "mock"},
        files={"file": ("novel.txt", text.encode("gbk"), "text/plain")},
    )
    result = client.get(f"/runs/{run_id}")
    assert result.status_code == 200
    assert "质量报告" in result.text


def test_run_with_chapter_range_then_rerun() -> None:
    novel = _multi_chapter_novel(5)
    run_id = _run(
        data={"provider": "mock", "chapter_start": "2", "chapter_end": "4"},
        files={"file": ("novel.txt", novel, "text/plain")},
    )
    result = client.get(f"/runs/{run_id}")
    assert "原著共 5 章" in result.text
    assert "本次转换第 2" in result.text

    # Re-run a different range from the already-staged source (no re-upload).
    rerun = client.post(f"/runs/{run_id}/rerun", data={"chapter_start": "1", "chapter_end": "5"})
    assert rerun.status_code == 200  # running page
    _await_run(run_id)
    assert "本次转换第 1" in client.get(f"/runs/{run_id}").text


def test_too_small_chapter_range_surfaces_error() -> None:
    run_id = _run(
        data={"provider": "mock", "chapter_start": "1", "chapter_end": "2"},
        files={"file": ("novel.txt", _multi_chapter_novel(5), "text/plain")},
    )
    result = client.get(f"/runs/{run_id}")
    assert result.status_code == 400
    assert "不足" in result.text


def test_events_for_unknown_run_emits_terminal_frame() -> None:
    # An untracked run (restart/eviction/stale link) must not 404 into an
    # infinite EventSource retry; it returns one terminal frame and closes.
    with client.stream("GET", "/runs/aaaaaaaaaaaa/events") as stream:
        frames = [line for line in stream.iter_lines() if line.startswith("data:")]
    assert frames == ['data: {"stage": "complete", "status": "done"}']


def test_download_rejects_invalid_run_id() -> None:
    # Non-token run ids (e.g. traversal attempts) must not resolve to a path.
    assert client.get("/runs/not-a-token/download/yaml").status_code == 404
    assert client.get("/runs/..%2f..%2fetc/download/yaml").status_code == 404


def test_run_rejects_unsupported_file() -> None:
    response = client.post(
        "/runs",
        data={"provider": "mock"},
        files={"file": ("novel.pdf", b"not supported", "application/pdf")},
    )
    assert response.status_code == 400
    assert "只支持" in response.text
