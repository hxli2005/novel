import json
from pathlib import Path

from novel_to_screenplay.pipeline.chapter_parser import parse_chapters_file
from novel_to_screenplay.pipeline.entity_analyzer import (
    analyze_chapters,
    analyze_chapters_auto,
    analyze_chapters_with_llm,
    merge_segment_payloads,
    resolve_aliases,
    split_text_into_chunks,
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


def test_split_text_into_chunks_packs_paragraphs_within_limit() -> None:
    text = "\n\n".join(["甲" * 30, "乙" * 30, "丙" * 30])

    chunks = split_text_into_chunks(text, 50)

    assert len(chunks) >= 2
    assert all(len(chunk) <= 50 for chunk in chunks)
    # Short text stays a single chunk.
    assert split_text_into_chunks("一段短文。", 50) == ["一段短文。"]


def test_merge_segment_payloads_concatenates_lists_and_joins_summaries() -> None:
    merged = merge_segment_payloads(
        [
            {"summary": "前半", "characters": ["甲"], "locations": ["房间"], "events": ["e1"]},
            {"summary": "后半", "characters": ["乙"], "locations": [], "events": ["e2"]},
        ]
    )

    assert merged["summary"] == "前半 后半"
    assert merged["characters"] == ["甲", "乙"]
    assert merged["events"] == ["e1", "e2"]


def test_resolve_aliases_merges_chinese_short_forms() -> None:
    mapping = resolve_aliases(["李慕白", "慕白", "柳含烟", "含烟", "老板", "赵无极"])
    assert mapping["慕白"] == "李慕白"
    assert mapping["含烟"] == "柳含烟"
    assert mapping["老板"] == "老板"
    assert mapping["李慕白"] == "李慕白"

    # Location-style suffix (新公寓 contains 公寓).
    assert resolve_aliases(["新公寓", "公寓"])["公寓"] == "新公寓"

    # A shared-surname *prefix* must NOT merge two distinct names.
    distinct = resolve_aliases(["张伟", "张伟杰"])
    assert distinct["张伟"] == "张伟"
    assert distinct["张伟杰"] == "张伟杰"

    # A suffix shared by two full names is ambiguous -> kept as its own entity.
    ambiguous = resolve_aliases(["李慕白", "张慕白", "慕白"])
    assert ambiguous["慕白"] == "慕白"
    assert ambiguous["李慕白"] == "李慕白"
    assert ambiguous["张慕白"] == "张慕白"


def test_analyze_chapters_with_llm_merges_aliases_across_chapters() -> None:
    chapters = parse_chapters_file(FIXTURE)
    provider = FakeAnalysisProvider(
        [
            {"summary": "一", "characters": ["慕白"], "locations": ["客栈"]},
            {"summary": "二", "characters": ["李慕白"], "locations": ["悦来客栈"]},
            {"summary": "三", "characters": ["柳含烟", "含烟"], "locations": []},
        ]
    )

    analysis = analyze_chapters_with_llm(chapters, provider)

    assert {character.name for character in analysis.characters} == {"李慕白", "柳含烟"}
    mubai = next(character for character in analysis.characters if character.name == "李慕白")
    assert mubai.source_chapters == ["ch_001", "ch_002"]
    # The canonical name also replaces the short form in the per-chapter list.
    assert analysis.chapter_analyses[0].characters == ["李慕白"]
    # Location aliases merge too (客栈 -> 悦来客栈), with the same propagation:
    assert {location.name for location in analysis.locations} == {"悦来客栈"}
    assert analysis.chapter_analyses[0].locations == ["悦来客栈"]
    inn = next(location for location in analysis.locations if location.name == "悦来客栈")
    assert inn.source_chapters == ["ch_001", "ch_002"]


def test_analyze_chapters_with_llm_chunks_long_chapters() -> None:
    chapters = parse_chapters_file(FIXTURE)
    provider = FakeAnalysisProvider(
        [
            {
                "summary": "段落梗概。",
                "characters": ["甲"],
                "locations": ["房间"],
                "events": ["事件"],
                "possible_setups": [],
            }
        ]
    )

    analysis = analyze_chapters_with_llm(chapters, provider, max_chars=40)

    # A small max_chars forces each chapter into several segment calls.
    assert provider.calls > len(chapters)
    assert {character.name for character in analysis.characters} == {"甲"}
