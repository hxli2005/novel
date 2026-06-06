from pathlib import Path

from novel_to_screenplay.pipeline.chapter_parser import parse_chapters_file
from novel_to_screenplay.pipeline.entity_analyzer import analyze_chapters


def test_analyze_chapters_extracts_sample_entities() -> None:
    fixture = Path(__file__).resolve().parents[1] / "examples" / "novels" / "three_chapters.txt"
    chapters = parse_chapters_file(fixture)

    analysis = analyze_chapters(chapters)

    character_names = {character.name for character in analysis.characters}
    location_names = {location.name for location in analysis.locations}

    assert {"林青", "周叔", "赵岚", "顾明远"}.issubset(character_names)
    assert {"江城第三医院", "档案室", "药品库", "天台"}.issubset(location_names)
    assert len(analysis.chapter_analyses) == 3
    assert analysis.chapter_analyses[0].events
    assert analysis.chapter_analyses[0].possible_setups


def test_analyze_chapters_tracks_entity_source_chapters() -> None:
    fixture = Path(__file__).resolve().parents[1] / "examples" / "novels" / "three_chapters.txt"
    chapters = parse_chapters_file(fixture)

    analysis = analyze_chapters(chapters)

    lin_qing = next(character for character in analysis.characters if character.name == "林青")
    rooftop = next(location for location in analysis.locations if location.name == "天台")

    assert lin_qing.source_chapters == ["ch_001", "ch_002", "ch_003"]
    assert rooftop.source_chapters == ["ch_003"]
