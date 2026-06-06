from pathlib import Path

import yaml

from novel_to_screenplay.pipeline.chapter_parser import parse_chapters_file
from novel_to_screenplay.pipeline.entity_analyzer import analyze_chapters
from novel_to_screenplay.pipeline.scene_outliner import build_scene_outline
from novel_to_screenplay.pipeline.screenplay_generator import (
    ScreenplayGenerationOptions,
    build_screenplay_document,
    write_screenplay_yaml,
)
from novel_to_screenplay.pipeline.screenplay_validator import validate_screenplay_file

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "screenplay.schema.json"


def test_validate_screenplay_file_accepts_generated_document(tmp_path: Path) -> None:
    document = build_fixture_document()
    screenplay_path = tmp_path / "screenplay.yaml"
    write_screenplay_yaml(document, screenplay_path)

    result = validate_screenplay_file(screenplay_path, SCHEMA_PATH)

    assert result.passed
    assert result.issues == []


def test_validate_screenplay_file_reports_unknown_character_reference(tmp_path: Path) -> None:
    document = build_fixture_document()
    document["scenes"][0]["characters_present"] = ["char_missing"]
    screenplay_path = tmp_path / "screenplay.yaml"
    screenplay_path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")

    result = validate_screenplay_file(screenplay_path, SCHEMA_PATH)

    assert not result.passed
    assert result.issues[0].code == "UNKNOWN_CHARACTER_REF"
    assert result.issues[0].path == "/scenes/0/characters_present/0"


def test_validate_screenplay_file_reports_schema_errors(tmp_path: Path) -> None:
    document = build_fixture_document()
    del document["metadata"]["title"]
    screenplay_path = tmp_path / "screenplay.yaml"
    screenplay_path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")

    result = validate_screenplay_file(screenplay_path, SCHEMA_PATH)

    assert not result.passed
    assert any(issue.code == "SCHEMA_ERROR" for issue in result.issues)


def build_fixture_document() -> dict:
    fixture = Path(__file__).resolve().parents[1] / "examples" / "novels" / "three_chapters.txt"
    chapters = parse_chapters_file(fixture)
    analysis = analyze_chapters(chapters)
    outline = build_scene_outline(analysis)
    return build_screenplay_document(
        chapters,
        analysis,
        outline,
        ScreenplayGenerationOptions(
            title="第七页",
            author="示例作者",
            created_at="2026-06-06T10:00:00+08:00",
        ),
    )
