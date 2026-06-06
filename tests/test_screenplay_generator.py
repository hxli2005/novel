from pathlib import Path

from novel_to_screenplay.pipeline.chapter_parser import parse_chapters_file
from novel_to_screenplay.pipeline.entity_analyzer import analyze_chapters
from novel_to_screenplay.pipeline.scene_outliner import build_scene_outline
from novel_to_screenplay.pipeline.screenplay_generator import (
    SCHEMA_VERSION,
    ScreenplayGenerationOptions,
    build_screenplay_document,
    dump_yaml,
)


def test_build_screenplay_document_creates_schema_ready_top_level_fields() -> None:
    fixture = Path(__file__).resolve().parents[1] / "examples" / "novels" / "three_chapters.txt"
    chapters = parse_chapters_file(fixture)
    analysis = analyze_chapters(chapters)
    outline = build_scene_outline(analysis)

    document = build_screenplay_document(
        chapters,
        analysis,
        outline,
        ScreenplayGenerationOptions(
            title="第七页",
            author="示例作者",
            created_at="2026-06-06T10:00:00+08:00",
        ),
    )

    assert document["schema_version"] == SCHEMA_VERSION
    assert document["metadata"]["title"] == "第七页"
    assert document["source"]["chapter_count"] == 3
    assert len(document["characters"]) >= 3
    assert len(document["locations"]) >= 3
    assert len(document["scenes"]) == 3
    assert document["scenes"][0]["chapter_refs"] == ["ch_001"]
    assert document["scenes"][0]["script"][0]["type"] == "action"
    assert document["quality_report"]["validation_status"] == "warning"
    assert document["quality_report"]["chapter_coverage"][0]["used_in_scene_ids"] == ["sc_001"]


def test_dump_yaml_writes_nested_screenplay_sections() -> None:
    fixture = Path(__file__).resolve().parents[1] / "examples" / "novels" / "three_chapters.txt"
    chapters = parse_chapters_file(fixture)
    analysis = analyze_chapters(chapters)
    outline = build_scene_outline(analysis)

    yaml_text = dump_yaml(
        build_screenplay_document(
            chapters,
            analysis,
            outline,
            ScreenplayGenerationOptions(
                title="第七页",
                author="示例作者",
                created_at="2026-06-06T10:00:00+08:00",
            ),
        )
    )

    assert 'schema_version: "screenplay_yaml/v0.1"' in yaml_text
    assert "source:" in yaml_text
    assert "characters:" in yaml_text
    assert "locations:" in yaml_text
    assert "structure:" in yaml_text
    assert "scenes:" in yaml_text
    assert "quality_report:" in yaml_text
