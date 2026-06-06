from pathlib import Path

from novel_to_screenplay.pipeline.chapter_parser import parse_chapters_file
from novel_to_screenplay.pipeline.entity_analyzer import analyze_chapters
from novel_to_screenplay.pipeline.scene_outliner import build_scene_outline


def test_build_scene_outline_creates_one_scene_per_chapter() -> None:
    fixture = Path(__file__).resolve().parents[1] / "examples" / "novels" / "three_chapters.txt"
    analysis = analyze_chapters(parse_chapters_file(fixture))

    outline = build_scene_outline(analysis)

    assert [scene.id for scene in outline.scenes] == ["sc_001", "sc_002", "sc_003"]
    assert [scene.chapter_refs for scene in outline.scenes] == [["ch_001"], ["ch_002"], ["ch_003"]]
    assert outline.scenes[0].dramatic_function == "inciting_incident"
    assert outline.scenes[1].dramatic_function == "development"
    assert outline.scenes[2].dramatic_function == "payoff"


def test_build_scene_outline_references_entity_ids_and_specific_locations() -> None:
    fixture = Path(__file__).resolve().parents[1] / "examples" / "novels" / "three_chapters.txt"
    analysis = analyze_chapters(parse_chapters_file(fixture))

    outline = build_scene_outline(analysis)

    assert "char_002" in outline.scenes[0].characters_present
    assert outline.scenes[0].scene_heading.display == "档案室"
    assert outline.scenes[1].scene_heading.display in {"医院旧楼", "地下药品库", "药品库"}
    assert outline.scenes[2].scene_heading.display in {"住院楼天台", "天台"}
    assert outline.scenes[0].required_events
