from pathlib import Path

from typer.testing import CliRunner

from novel_to_screenplay import __version__
from novel_to_screenplay.cli import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert f"novel2script {__version__}" in result.stdout


def test_status_command() -> None:
    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "CLI skeleton is ready" in result.stdout


def test_run_dry_run_validates_input_without_creating_workspace(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    source.write_text("第一章\n故事开始。", encoding="utf-8")
    output_dir = tmp_path / "run"

    result = runner.invoke(
        app,
        ["run", str(source), "--out", str(output_dir), "--provider", "mock", "--dry-run"],
    )

    assert result.exit_code == 0
    assert "Ready to run with provider 'mock'" in result.stdout
    assert not output_dir.exists()


def test_run_initializes_workspace_and_stages_source(tmp_path: Path) -> None:
    source = tmp_path / "novel.md"
    source.write_text("# 第一章\n故事开始。", encoding="utf-8")
    output_dir = tmp_path / "run"

    result = runner.invoke(app, ["run", str(source), "--out", str(output_dir)])

    assert result.exit_code == 0
    assert (output_dir / "input" / "source.md").read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )
    assert (output_dir / "intermediates").is_dir()
    assert (output_dir / "index").is_dir()


def test_run_rejects_unsupported_input_suffix(tmp_path: Path) -> None:
    source = tmp_path / "novel.pdf"
    source.write_text("not a supported input", encoding="utf-8")

    result = runner.invoke(app, ["run", str(source), "--dry-run"])

    assert result.exit_code != 0
    assert "input file must use one of" in result.output


def test_parse_command_writes_parsed_chapters_yaml(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    source.write_text(
        "\n\n".join(
            [
                "第一章 开端\n主角发现线索。",
                "第二章 调查\n主角进入旧楼。",
                "第三章 揭露\n真相浮出水面。",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "run"

    result = runner.invoke(app, ["parse", str(source), "--out", str(output_dir)])

    assert result.exit_code == 0
    parsed = output_dir / "intermediates" / "parsed_chapters.yaml"
    assert parsed.is_file()
    parsed_text = parsed.read_text(encoding="utf-8")
    assert "Parsed chapters: 3" in result.stdout
    assert 'id: "ch_001"' in parsed_text
    assert 'title: "第一章 开端"' in parsed_text
    assert "sha256:" in parsed_text


def test_parse_command_rejects_fewer_than_three_chapters(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    source.write_text("第一章 开端\n内容。\n\n第二章 继续\n内容。", encoding="utf-8")

    result = runner.invoke(app, ["parse", str(source), "--out", str(tmp_path / "run")])

    assert result.exit_code != 0
    assert "At least 3 chapters are required" in result.output
