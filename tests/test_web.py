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


def test_run_rejects_unsupported_file() -> None:
    response = client.post(
        "/runs",
        data={"provider": "mock"},
        files={"file": ("novel.pdf", b"not supported", "application/pdf")},
    )
    assert response.status_code == 400
    assert "只支持" in response.text
