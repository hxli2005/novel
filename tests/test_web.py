from fastapi.testclient import TestClient

from novel_to_screenplay.web.app import app

client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_renders_upload_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "墨稿" in response.text
    assert "开始改编" in response.text


def test_run_sample_end_to_end_and_downloads() -> None:
    # Use the bundled sample with the offline mock provider.
    response = client.post("/runs", data={"use_sample": "1", "provider": "mock"})
    assert response.status_code == 200  # followed the 303 redirect to the result page
    assert "质量报告" in response.text
    # The result page renders a screenplay with extracted characters.
    assert "林青" in response.text

    run_id = response.url.path.rsplit("/", 1)[-1]
    for fmt in ["yaml", "fountain", "docx"]:
        download = client.get(f"/runs/{run_id}/download/{fmt}")
        assert download.status_code == 200, fmt
        assert download.content, fmt


def test_run_accepts_gbk_encoded_upload() -> None:
    # Chinese novels are frequently GBK-encoded; this must not 500.
    text = "第一章 起\n中文内容。\n\n第二章 承\n更多内容。\n\n第三章 合\n结尾。\n"
    response = client.post(
        "/runs",
        data={"provider": "mock"},
        files={"file": ("novel.txt", text.encode("gbk"), "text/plain")},
    )
    assert response.status_code == 200
    assert "质量报告" in response.text


def _multi_chapter_novel(count: int) -> bytes:
    return "\n\n".join(f"第{i}章 标题{i}\n内容{i}。" for i in range(1, count + 1)).encode("utf-8")


def test_run_with_chapter_range_then_rerun() -> None:
    novel = _multi_chapter_novel(5)
    response = client.post(
        "/runs",
        data={"provider": "mock", "chapter_start": "2", "chapter_end": "4"},
        files={"file": ("novel.txt", novel, "text/plain")},
    )
    assert response.status_code == 200
    assert "原著共 5 章" in response.text
    assert "本次转换第 2" in response.text

    run_id = response.url.path.rsplit("/", 1)[-1]
    # Re-run a different range from the already-staged source (no re-upload).
    rerun = client.post(f"/runs/{run_id}/rerun", data={"chapter_start": "1", "chapter_end": "5"})
    assert rerun.status_code == 200
    assert "本次转换第 1" in rerun.text


def test_run_rejects_too_small_chapter_range() -> None:
    response = client.post(
        "/runs",
        data={"provider": "mock", "chapter_start": "1", "chapter_end": "2"},
        files={"file": ("novel.txt", _multi_chapter_novel(5), "text/plain")},
    )
    assert response.status_code == 400
    assert "不足" in response.text


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
