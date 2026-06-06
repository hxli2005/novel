import json
from pathlib import Path

from novel_to_screenplay.pipeline.chapter_parser import parse_chapters_file
from novel_to_screenplay.pipeline.entity_analyzer import analyze_chapters
from novel_to_screenplay.pipeline.scene_outliner import (
    build_scene_outline,
    build_scene_outline_auto,
    build_scene_outline_with_llm,
)
from novel_to_screenplay.providers import ChatMessage, MockProvider, ProviderCompletion

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "novels" / "three_chapters.txt"


class StaticOutlineProvider:
    """Provider that returns one fixed JSON outline regardless of the prompt."""

    name = "fake"
    model = "fake-outline-model"

    def __init__(self, scenes: object) -> None:
        self.scenes = scenes

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> ProviderCompletion:
        del messages, temperature, max_tokens
        return ProviderCompletion(
            text=json.dumps(self.scenes, ensure_ascii=False),
            provider=self.name,
            model=self.model,
            usage={},
        )


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


def test_build_scene_outline_with_llm_can_split_a_chapter() -> None:
    analysis = analyze_chapters(parse_chapters_file(FIXTURE))
    provider = StaticOutlineProvider(
        [
            {
                "chapter_refs": ["ch_001"],
                "location_id": "loc_001",
                "display": "档案室",
                "location_mode": "int",
                "time_of_day": "night",
                "summary": "林青潜入档案室。",
                "dramatic_function": "inciting_incident",
                "characters_present": ["char_001"],
                "required_event_ids": ["evt_raw_001"],
                "setup_notes": ["第七页"],
            },
            {
                "chapter_refs": ["ch_001", "ch_002"],
                "display": "走廊",
                "summary": "追逐与逃离。",
                "characters_present": ["char_001"],
            },
        ]
    )

    outline = build_scene_outline_with_llm(analysis, provider)

    assert [scene.id for scene in outline.scenes] == ["sc_001", "sc_002"]
    assert outline.scenes[0].scene_heading.location_mode == "INT"
    assert outline.scenes[0].scene_heading.time_of_day == "NIGHT"
    assert outline.scenes[1].chapter_refs == ["ch_001", "ch_002"]
    # No location_id provided -> falls back to the display string.
    assert outline.scenes[1].scene_heading.display == "走廊"


def test_build_scene_outline_with_llm_drops_unknown_ids_and_scenes() -> None:
    analysis = analyze_chapters(parse_chapters_file(FIXTURE))
    provider = StaticOutlineProvider(
        [
            {
                "chapter_refs": ["ch_001", "ch_999"],
                "summary": "有效场景。",
                "characters_present": ["char_001", "char_missing"],
                "required_event_ids": ["evt_raw_001", "evt_bogus"],
            },
            {
                "chapter_refs": ["ch_404"],
                "summary": "整场引用了不存在的章节，应被丢弃。",
            },
            {"summary": "缺少 chapter_refs，应被丢弃。"},
        ]
    )

    outline = build_scene_outline_with_llm(analysis, provider)

    assert len(outline.scenes) == 1
    scene = outline.scenes[0]
    assert scene.chapter_refs == ["ch_001"]
    assert scene.characters_present == ["char_001"]
    assert scene.required_events == ["evt_raw_001"]


def test_build_scene_outline_with_llm_falls_back_when_empty() -> None:
    analysis = analyze_chapters(parse_chapters_file(FIXTURE))
    provider = StaticOutlineProvider([])

    outline = build_scene_outline_with_llm(analysis, provider)

    # Empty model output falls back to the rule-based one-scene-per-chapter outline.
    assert [scene.id for scene in outline.scenes] == ["sc_001", "sc_002", "sc_003"]


def test_build_scene_outline_with_llm_falls_back_on_malformed_response() -> None:
    analysis = analyze_chapters(parse_chapters_file(FIXTURE))

    class MalformedProvider:
        name = "fake"
        model = "fake-outline-model"

        def complete(self, messages, *, temperature=0.2, max_tokens=2048):  # type: ignore[no-untyped-def]
            del messages, temperature, max_tokens
            return ProviderCompletion(
                text="抱歉，我无法返回 JSON。", provider=self.name, model=self.model, usage={}
            )

    outline = build_scene_outline_with_llm(analysis, MalformedProvider())

    # A non-JSON response (even after the repair retry) falls back to rules.
    assert [scene.id for scene in outline.scenes] == ["sc_001", "sc_002", "sc_003"]


def test_build_scene_outline_auto_uses_rules_for_mock_provider() -> None:
    analysis = analyze_chapters(parse_chapters_file(FIXTURE))

    outline = build_scene_outline_auto(analysis, MockProvider())

    assert [scene.chapter_refs for scene in outline.scenes] == [["ch_001"], ["ch_002"], ["ch_003"]]
