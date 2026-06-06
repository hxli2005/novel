from pathlib import Path

import yaml
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
    assert "pipeline is ready through screenplay YAML draft generation" in result.stdout


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


def test_run_rejects_unknown_provider(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    source.write_text("第一章\n故事开始。", encoding="utf-8")

    result = runner.invoke(
        app,
        ["run", str(source), "--provider", "unknown", "--dry-run"],
    )

    assert result.exit_code != 0
    assert "Unsupported provider" in result.output


def test_providers_command_lists_supported_providers() -> None:
    result = runner.invoke(app, ["providers"], env={"DEEPSEEK_API_KEY": ""})

    assert result.exit_code == 0
    assert "mock: configured" in result.stdout
    assert "deepseek: missing config" in result.stdout


def test_check_provider_uses_mock_provider() -> None:
    result = runner.invoke(
        app,
        ["check-provider", "--provider", "mock", "--prompt", "确认连通。"],
    )

    assert result.exit_code == 0
    assert "Provider: mock" in result.stdout
    assert "Model: mock" in result.stdout
    assert "mock response: 确认连通。" in result.stdout


def test_check_provider_reports_missing_deepseek_key() -> None:
    result = runner.invoke(
        app,
        ["check-provider", "--provider", "deepseek"],
        env={"DEEPSEEK_API_KEY": ""},
    )

    assert result.exit_code != 0
    assert "DEEPSEEK_API_KEY is required" in result.stdout


def test_run_executes_parse_and_analyze_pipeline(tmp_path: Path) -> None:
    source = tmp_path / "novel.md"
    source.write_text(
        "\n\n".join(
            [
                "# 第一章 档案室\n林青在档案室发现线索。周叔说不要再查。",
                "# 第二章 药品库\n林青进入药品库。主刀医生顾明远的名字出现。",
                "# 第三章 天台\n赵岚走上天台。林青按下录音笔。",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "run"

    result = runner.invoke(app, ["run", str(source), "--out", str(output_dir)])

    assert result.exit_code == 0
    assert (output_dir / "input" / "source.md").read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )
    assert (output_dir / "intermediates").is_dir()
    assert (output_dir / "index").is_dir()
    assert (output_dir / "intermediates" / "parsed_chapters.yaml").is_file()
    assert (output_dir / "intermediates" / "chapter_analysis.yaml").is_file()
    assert (output_dir / "intermediates" / "characters.yaml").is_file()
    assert (output_dir / "intermediates" / "locations.yaml").is_file()
    assert (output_dir / "intermediates" / "scene_outline.yaml").is_file()
    assert (output_dir / "output" / "screenplay.yaml").is_file()
    assert "Parsed chapters: 3" in result.stdout
    assert "Analyzed chapters: 3" in result.stdout
    assert "Outlined scenes: 3" in result.stdout
    assert "Generated screenplay:" in result.stdout


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


def test_analyze_command_writes_entity_analysis_outputs(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    source.write_text(
        "\n\n".join(
            [
                "第一章 档案室\n林青在档案室发现线索。周叔说不要再查。",
                "第二章 药品库\n林青进入药品库。主刀医生顾明远的名字出现。",
                "第三章 天台\n赵岚走上天台。林青按下录音笔。",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "run"

    parse_result = runner.invoke(app, ["parse", str(source), "--out", str(output_dir)])
    analyze_result = runner.invoke(app, ["analyze", str(output_dir)])

    assert parse_result.exit_code == 0
    assert analyze_result.exit_code == 0
    assert "Analyzed chapters: 3" in analyze_result.stdout
    assert (output_dir / "intermediates" / "chapter_analysis.yaml").is_file()
    assert (output_dir / "intermediates" / "characters.yaml").is_file()
    assert (output_dir / "intermediates" / "locations.yaml").is_file()

    characters_text = (output_dir / "intermediates" / "characters.yaml").read_text(encoding="utf-8")
    locations_text = (output_dir / "intermediates" / "locations.yaml").read_text(encoding="utf-8")
    assert 'name: "林青"' in characters_text
    assert 'name: "顾明远"' in characters_text
    assert 'name: "档案室"' in locations_text


def test_analyze_command_requires_staged_source(tmp_path: Path) -> None:
    workspace = tmp_path / "run"
    workspace.mkdir()

    result = runner.invoke(app, ["analyze", str(workspace)])

    assert result.exit_code != 0
    assert "No staged source file found. Run novel2script parse first." in result.output


def test_outline_command_writes_scene_outline(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    source.write_text(
        "\n\n".join(
            [
                "第一章 档案室\n林青在档案室发现线索。周叔说不要再查。",
                "第二章 药品库\n林青进入药品库。主刀医生顾明远的名字出现。",
                "第三章 天台\n赵岚走上天台。林青按下录音笔。",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "run"

    parse_result = runner.invoke(app, ["parse", str(source), "--out", str(output_dir)])
    outline_result = runner.invoke(app, ["outline", str(output_dir)])

    assert parse_result.exit_code == 0
    assert outline_result.exit_code == 0
    outline_file = output_dir / "intermediates" / "scene_outline.yaml"
    assert outline_file.is_file()
    outline_text = outline_file.read_text(encoding="utf-8")
    assert "Outlined scenes: 3" in outline_result.stdout
    assert 'id: "sc_001"' in outline_text
    assert "chapter_refs:" in outline_text
    assert 'dramatic_function: "inciting_incident"' in outline_text


def test_generate_command_writes_screenplay_yaml(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    source.write_text(
        "\n\n".join(
            [
                "第一章 档案室\n林青在档案室发现线索。周叔说不要再查。",
                "第二章 药品库\n林青进入药品库。主刀医生顾明远的名字出现。",
                "第三章 天台\n赵岚走上天台。林青按下录音笔。",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "run"

    parse_result = runner.invoke(app, ["parse", str(source), "--out", str(output_dir)])
    generate_result = runner.invoke(
        app,
        ["generate", str(output_dir), "--title", "第七页", "--author", "示例作者"],
    )

    assert parse_result.exit_code == 0
    assert generate_result.exit_code == 0
    screenplay_file = output_dir / "output" / "screenplay.yaml"
    assert screenplay_file.is_file()
    screenplay_text = screenplay_file.read_text(encoding="utf-8")
    assert "Generated screenplay:" in generate_result.stdout
    assert 'schema_version: "screenplay_yaml/v0.1"' in screenplay_text
    assert 'title: "第七页"' in screenplay_text
    assert "quality_report:" in screenplay_text
    assert "script:" in screenplay_text


def test_validate_command_accepts_generated_screenplay_yaml(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    source.write_text(
        "\n\n".join(
            [
                "第一章 档案室\n林青在档案室发现线索。周叔说不要再查。",
                "第二章 药品库\n林青进入药品库。主刀医生顾明远的名字出现。",
                "第三章 天台\n赵岚走上天台。林青按下录音笔。",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "run"

    run_result = runner.invoke(app, ["run", str(source), "--out", str(output_dir)])
    validate_result = runner.invoke(app, ["validate", str(output_dir)])

    assert run_result.exit_code == 0
    assert validate_result.exit_code == 0
    assert "Validation passed:" in validate_result.stdout


def test_draft_scenes_command_updates_screenplay_and_still_validates(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    source.write_text(
        "\n\n".join(
            [
                "第一章 档案室\n林青在档案室发现线索。周叔说不要再查。",
                "第二章 药品库\n林青进入药品库。主刀医生顾明远的名字出现。",
                "第三章 天台\n赵岚走上天台。林青按下录音笔。",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "run"

    run_result = runner.invoke(app, ["run", str(source), "--out", str(output_dir)])
    draft_result = runner.invoke(app, ["draft-scenes", str(output_dir), "--provider", "mock"])
    validate_result = runner.invoke(app, ["validate", str(output_dir)])

    screenplay_path = output_dir / "output" / "screenplay.yaml"
    document = yaml.safe_load(screenplay_path.read_text(encoding="utf-8"))

    assert run_result.exit_code == 0
    assert draft_result.exit_code == 0
    assert validate_result.exit_code == 0
    assert "Drafted scenes: 3" in draft_result.stdout
    assert document["scenes"][0]["revision_status"] == "ai_drafted"
    assert document["quality_report"]["warnings"][-1]["code"] == "AI_SCENE_DRAFTING"


def test_draft_scenes_command_requires_screenplay_yaml(tmp_path: Path) -> None:
    workspace = tmp_path / "run"
    workspace.mkdir()

    result = runner.invoke(app, ["draft-scenes", str(workspace)])

    assert result.exit_code != 0
    assert "No screenplay file found. Run novel2script generate first." in result.stdout


def test_validate_command_reports_unknown_id_references(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    source.write_text(
        "\n\n".join(
            [
                "第一章 档案室\n林青在档案室发现线索。周叔说不要再查。",
                "第二章 药品库\n林青进入药品库。主刀医生顾明远的名字出现。",
                "第三章 天台\n赵岚走上天台。林青按下录音笔。",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "run"

    run_result = runner.invoke(app, ["run", str(source), "--out", str(output_dir)])
    screenplay_path = output_dir / "output" / "screenplay.yaml"
    document = yaml.safe_load(screenplay_path.read_text(encoding="utf-8"))
    document["scenes"][0]["characters_present"] = ["char_missing"]
    screenplay_path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    validate_result = runner.invoke(app, ["validate", str(output_dir)])

    assert run_result.exit_code == 0
    assert validate_result.exit_code != 0
    assert "Validation failed:" in validate_result.stdout
    assert "UNKNOWN_CHARACTER_REF" in validate_result.stdout
