import json
from pathlib import Path

from novel_to_screenplay.pipeline.chapter_parser import parse_chapters_file
from novel_to_screenplay.pipeline.entity_analyzer import (
    analyze_chapters,
    analyze_chapters_auto,
    analyze_chapters_with_llm,
)
from novel_to_screenplay.providers import ChatMessage, MockProvider, ProviderCompletion

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "novels" / "three_chapters.txt"


class FakeAnalysisProvider:
    """Provider that returns one scripted JSON payload per chapter call."""

    name = "fake"
    model = "fake-analysis-model"

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads
        self.calls = 0

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> ProviderCompletion:
        del messages, temperature, max_tokens
        payload = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        return ProviderCompletion(
            text=json.dumps(payload, ensure_ascii=False),
            provider=self.name,
            model=self.model,
            usage={},
        )


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


def test_analyze_chapters_with_llm_is_provider_driven() -> None:
    chapters = parse_chapters_file(FIXTURE)
    # Names absent from the demo text prove extraction comes from the provider,
    # not the rule-based regex.
    provider = FakeAnalysisProvider(
        [
            {
                "summary": "舰队起航。",
                "characters": ["艾拉", "船长"],
                "locations": ["甲板"],
                "events": ["舰队驶离港口"],
                "possible_setups": ["一封神秘信件"],
            },
            {
                "summary": "货舱中的发现。",
                "characters": ["艾拉"],
                "locations": ["货舱"],
                "events": ["发现密室"],
                "possible_setups": [],
            },
            {
                "summary": "甲板上的对峙。",
                "characters": ["船长", "叛徒"],
                "locations": ["甲板"],
                "events": ["正面冲突"],
                "possible_setups": [],
            },
        ]
    )

    analysis = analyze_chapters_with_llm(chapters, provider)

    assert provider.calls == 3
    assert {character.name for character in analysis.characters} == {"艾拉", "船长", "叛徒"}
    aila = next(character for character in analysis.characters if character.name == "艾拉")
    assert aila.source_chapters == ["ch_001", "ch_002"]
    assert analysis.chapter_analyses[0].summary == "舰队起航。"
    assert analysis.chapter_analyses[0].possible_setups[0].summary == "一封神秘信件"


def test_analyze_chapters_auto_uses_rules_for_mock_provider() -> None:
    chapters = parse_chapters_file(FIXTURE)

    analysis = analyze_chapters_auto(chapters, MockProvider())

    assert "林青" in {character.name for character in analysis.characters}
