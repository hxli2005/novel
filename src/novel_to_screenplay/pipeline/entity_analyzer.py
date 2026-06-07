"""Entity and chapter analysis extraction (rule-based and LLM-based)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from novel_to_screenplay.pipeline.chapter_parser import ParsedChapter, quote_yaml_scalar
from novel_to_screenplay.providers import ChatMessage, MockProvider
from novel_to_screenplay.structured_output import complete_json

MAX_EVENTS_PER_CHAPTER = 3
MAX_ENTITY_NAME_LENGTH = 40
CHUNK_CHAR_THRESHOLD = 4000

PERSON_STOPWORDS = {
    "主角",
    "父亲",
    "手术",
    "病历",
    "声音",
    "名字",
    "证据",
    "真相",
    "药品",
    "医院",
    "档案",
    "录音",
}
PERSON_BAD_PREFIXES = ("他", "她", "它")
PERSON_BAD_SUFFIXES = ("声", "有", "地", "你", "里", "推", "带", "追")

PERSON_VERB_PATTERN = re.compile(
    r"(?:^|[，。！？；、\s])"
    r"(?P<name>[\u4e00-\u9fff]{2,3})"
    r"(?=(?:说|问|承认|追问|没有|听出|戴着|离开|请假|按下|约|走进|走上|拿着))"
)
TITLED_PERSON_PATTERN = re.compile(
    r"(?:主刀医生|医生|助理|老保安|保安|主任)(?P<name>[\u4e00-\u9fff]{2,3})"
)

HOSPITAL_PATTERN = re.compile(
    r"(?:^|[，。！？；、\s])(?P<name>[\u4e00-\u9fff\d]{2,12}医院)(?!旧楼)"
)
LOCATION_BAD_SUBSTRINGS = ("去了", "属于", "这把", "请假")
LOCATION_TERMS = [
    "地下药品库",
    "住院楼天台",
    "医院旧楼",
    "档案室",
    "药品库",
    "楼梯间",
    "住院楼",
    "旧楼",
    "天台",
]

SETUP_KEYWORDS = [
    "第七页",
    "铜钥匙",
    "钥匙",
    "录音笔",
    "值班表",
    "铁盒",
    "手套",
]


@dataclass(frozen=True)
class ExtractedEntity:
    """A normalized extracted entity."""

    id: str
    name: str
    source_chapters: list[str]


@dataclass(frozen=True)
class ExtractedEvent:
    """A raw event candidate from one chapter."""

    id: str
    summary: str


@dataclass(frozen=True)
class SetupCandidate:
    """A possible setup or clue candidate."""

    summary: str


@dataclass(frozen=True)
class ChapterAnalysis:
    """Rule-based analysis for one chapter."""

    chapter_id: str
    summary: str
    characters: list[str]
    locations: list[str]
    events: list[ExtractedEvent]
    possible_setups: list[SetupCandidate]


@dataclass(frozen=True)
class EntityAnalysis:
    """All entity and chapter analysis outputs."""

    chapter_analyses: list[ChapterAnalysis]
    characters: list[ExtractedEntity]
    locations: list[ExtractedEntity]


def analyze_chapters(chapters: list[ParsedChapter]) -> EntityAnalysis:
    """Extract first-pass chapter analyses, characters, and locations."""

    chapter_analyses: list[ChapterAnalysis] = []
    character_sources: dict[str, set[str]] = {}
    location_sources: dict[str, set[str]] = {}
    event_counter = 1

    for chapter in chapters:
        characters = extract_character_names(chapter.text)
        locations = extract_location_names(chapter.text)
        events = []
        for event_summary in extract_event_summaries(chapter.text):
            events.append(ExtractedEvent(id=f"evt_raw_{event_counter:03d}", summary=event_summary))
            event_counter += 1

        possible_setups = [
            SetupCandidate(summary=setup) for setup in extract_setup_candidates(chapter.text)
        ]

        for character in characters:
            character_sources.setdefault(character, set()).add(chapter.id)
        for location in locations:
            location_sources.setdefault(location, set()).add(chapter.id)

        chapter_analyses.append(
            ChapterAnalysis(
                chapter_id=chapter.id,
                summary=build_chapter_summary(chapter),
                characters=characters,
                locations=locations,
                events=events,
                possible_setups=possible_setups,
            )
        )

    return EntityAnalysis(
        chapter_analyses=chapter_analyses,
        characters=build_entities("char", character_sources),
        locations=build_entities("loc", location_sources),
    )


def analyze_chapters_auto(chapters: list[ParsedChapter], provider: Any) -> EntityAnalysis:
    """Analyze chapters with the LLM provider, falling back to rules for mock."""

    if provider is None or isinstance(provider, MockProvider):
        return analyze_chapters(chapters)
    return analyze_chapters_with_llm(chapters, provider)


def analyze_chapters_with_llm(
    chapters: list[ParsedChapter],
    provider: Any,
    *,
    max_tokens: int = 1024,
    max_chars: int = CHUNK_CHAR_THRESHOLD,
) -> EntityAnalysis:
    """Extract chapter analyses and entities using an LLM provider.

    Each chapter is analyzed independently so prompts stay small and the work
    scales to longer novels; chapters longer than ``max_chars`` are split into
    segments, analyzed segment by segment, and merged. Results are aggregated
    into the same structures the rule-based path produces, keeping downstream
    stages unchanged.
    """

    raw_chapters: list[dict[str, Any]] = []
    event_counter = 1
    for chapter in chapters:
        payload = extract_chapter_payload(
            provider, chapter, max_tokens=max_tokens, max_chars=max_chars
        )

        events = []
        for event_summary in normalize_text_list(payload.get("events"))[:MAX_EVENTS_PER_CHAPTER]:
            events.append(ExtractedEvent(id=f"evt_raw_{event_counter:03d}", summary=event_summary))
            event_counter += 1

        summary = payload.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = build_chapter_summary(chapter)
        else:
            summary = truncate_text(" ".join(summary.split()), 90)

        raw_chapters.append(
            {
                "chapter_id": chapter.id,
                "summary": summary,
                "characters": normalize_name_list(payload.get("characters")),
                "locations": normalize_name_list(payload.get("locations")),
                "events": events,
                "possible_setups": [
                    SetupCandidate(summary=setup)
                    for setup in normalize_text_list(payload.get("possible_setups"))
                ],
            }
        )

    # Merge aliases across the whole novel (e.g. 慕白 -> 李慕白) before assigning ids,
    # since each chapter is analyzed in isolation and may use different name forms.
    character_aliases = resolve_aliases(name for raw in raw_chapters for name in raw["characters"])
    location_aliases = resolve_aliases(name for raw in raw_chapters for name in raw["locations"])

    chapter_analyses: list[ChapterAnalysis] = []
    character_sources: dict[str, set[str]] = {}
    location_sources: dict[str, set[str]] = {}
    for raw in raw_chapters:
        characters = sorted_unique([character_aliases[name] for name in raw["characters"]])
        locations = sorted_unique([location_aliases[name] for name in raw["locations"]])
        for character in characters:
            character_sources.setdefault(character, set()).add(raw["chapter_id"])
        for location in locations:
            location_sources.setdefault(location, set()).add(raw["chapter_id"])
        chapter_analyses.append(
            ChapterAnalysis(
                chapter_id=raw["chapter_id"],
                summary=raw["summary"],
                characters=characters,
                locations=locations,
                events=raw["events"],
                possible_setups=raw["possible_setups"],
            )
        )

    return EntityAnalysis(
        chapter_analyses=chapter_analyses,
        characters=build_entities("char", character_sources),
        locations=build_entities("loc", location_sources),
    )


def resolve_aliases(names: Iterable[str]) -> dict[str, str]:
    """Map each name to a canonical full name.

    Chinese short forms drop the surname, so a short name is a *suffix* of its
    full name (慕白 -> 李慕白, 公寓 -> 新公寓). A name (length >= 2) is folded into a
    longer canonical name only when it is a suffix of *exactly one* canonical;
    if several longer names share the suffix (李慕白 and 张慕白 both end with 慕白)
    the short form is ambiguous and kept as its own entity rather than guessed.
    Matching on suffix rather than arbitrary substring also avoids merging
    distinct names that merely share a surname prefix (张伟 vs 张伟杰). Erring
    toward under-merging keeps two real characters from collapsing into one.
    """

    canonicals: list[str] = []
    mapping: dict[str, str] = {}
    for name in sorted(set(names), key=lambda value: (-len(value), value)):
        if len(name) >= 2:
            matches = [
                canonical
                for canonical in canonicals
                if canonical != name and canonical.endswith(name)
            ]
        else:
            matches = []
        if len(matches) == 1:
            mapping[name] = matches[0]
        else:
            canonicals.append(name)
            mapping[name] = name
    return mapping


def extract_chapter_payload(
    provider: Any,
    chapter: ParsedChapter,
    *,
    max_tokens: int,
    max_chars: int = CHUNK_CHAR_THRESHOLD,
) -> dict[str, Any]:
    """Extract one chapter's analysis, splitting long chapters into segments."""

    segments = split_text_into_chunks(chapter.text, max_chars)
    if len(segments) <= 1:
        return extract_segment_payload(provider, chapter, chapter.text, max_tokens=max_tokens)
    segment_payloads = [
        extract_segment_payload(provider, chapter, segment, max_tokens=max_tokens)
        for segment in segments
    ]
    return merge_segment_payloads(segment_payloads)


def extract_segment_payload(
    provider: Any,
    chapter: ParsedChapter,
    text: str,
    *,
    max_tokens: int,
) -> dict[str, Any]:
    """Ask the provider to extract one chapter segment as a JSON object."""

    payload = complete_json(
        provider,
        build_chapter_analysis_prompt(chapter, text),
        expect="object",
        temperature=0.1,
        max_tokens=max_tokens,
    )
    return payload if isinstance(payload, dict) else {}


def split_text_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split text into <= max_chars chunks on paragraph boundaries."""

    units: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            units.append(paragraph)
        else:
            units.extend(
                paragraph[index : index + max_chars]
                for index in range(0, len(paragraph), max_chars)
            )

    chunks: list[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
        elif len(current) + 1 + len(unit) <= max_chars:
            current = f"{current}\n{unit}"
        else:
            chunks.append(current)
            current = unit
    if current:
        chunks.append(current)
    return chunks


def merge_segment_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge per-segment analysis payloads into one chapter payload.

    Lists are concatenated (downstream normalization dedups and caps them) and
    segment summaries are joined so the chapter summary spans the whole text.
    """

    summaries: list[str] = []
    characters: list[Any] = []
    locations: list[Any] = []
    events: list[Any] = []
    setups: list[Any] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        summary = payload.get("summary")
        if isinstance(summary, str) and summary.strip():
            summaries.append(summary.strip())
        characters.extend(_as_list(payload.get("characters")))
        locations.extend(_as_list(payload.get("locations")))
        events.extend(_as_list(payload.get("events")))
        setups.extend(_as_list(payload.get("possible_setups")))
    return {
        "summary": " ".join(summaries),
        "characters": characters,
        "locations": locations,
        "events": events,
        "possible_setups": setups,
    }


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_chapter_analysis_prompt(
    chapter: ParsedChapter,
    text: str | None = None,
) -> list[ChatMessage]:
    """Build the provider prompt for analyzing one chapter (or a segment)."""

    payload = {
        "chapter": {
            "id": chapter.id,
            "title": chapter.title,
            "text": chapter.text if text is None else text,
        },
        "output_contract": {
            "summary": "本章一句话剧情梗概",
            "characters": ["出场人物姓名，去重"],
            "locations": ["关键场景地点"],
            "events": ["按时间顺序的关键事件，最多 3 条"],
            "possible_setups": ["可能的伏笔或线索，没有则返回空数组"],
        },
    }
    return [
        ChatMessage(
            role="system",
            content=(
                "你是专业的中文小说改编分析助手。请阅读章节，抽取改编所需的结构化要素。"
                "只返回符合 output_contract 的 JSON 对象，不要 Markdown，不要解释。"
                "characters 只填真实出场的人物姓名，不要填代词或称谓。"
            ),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
        ),
    ]


def normalize_name_list(values: Any) -> list[str]:
    """Normalize a provider-supplied list of entity names."""

    if not isinstance(values, list):
        return []
    names = []
    for value in values:
        if not isinstance(value, str):
            continue
        name = value.strip()
        if name and len(name) <= MAX_ENTITY_NAME_LENGTH:
            names.append(name)
    return sorted_unique(names)


def normalize_text_list(values: Any) -> list[str]:
    """Normalize a provider-supplied list of free-text summaries."""

    if not isinstance(values, list):
        return []
    summaries = []
    for value in values:
        if not isinstance(value, str):
            continue
        summary = " ".join(value.split())
        if summary:
            summaries.append(truncate_text(summary, 90))
    return sorted_unique(summaries)


def extract_character_names(text: str) -> list[str]:
    """Extract likely character names using simple Chinese pattern rules."""

    candidates: list[str] = []
    for pattern in (PERSON_VERB_PATTERN, TITLED_PERSON_PATTERN):
        candidates.extend(match.group("name") for match in pattern.finditer(text))

    cleaned = []
    for candidate in candidates:
        name = candidate.strip("，。！？；、：“”\"'（）()")
        if name in PERSON_STOPWORDS:
            continue
        if name.startswith(PERSON_BAD_PREFIXES) or name.endswith(PERSON_BAD_SUFFIXES):
            continue
        if len(name) < 2 or len(name) > 4:
            continue
        cleaned.append(name)
    return sorted_unique(cleaned)


def extract_location_names(text: str) -> list[str]:
    """Extract recurring location names with conservative suffix matching."""

    locations: list[str] = []
    locations.extend(match.group("name") for match in HOSPITAL_PATTERN.finditer(text))
    locations.extend(term for term in LOCATION_TERMS if term in text)
    return sorted_unique(
        [location for location in locations if not has_bad_location_substring(location)]
    )


def extract_event_summaries(text: str) -> list[str]:
    """Use the first substantial paragraphs as raw event candidates."""

    paragraphs = split_body_paragraphs(text)
    event_summaries = []
    for paragraph in paragraphs:
        if len(paragraph) < 6:
            continue
        event_summaries.append(truncate_text(paragraph, 90))
        if len(event_summaries) >= MAX_EVENTS_PER_CHAPTER:
            break
    return event_summaries


def extract_setup_candidates(text: str) -> list[str]:
    """Extract paragraphs that mention clues likely to become setups."""

    setups = []
    for paragraph in split_body_paragraphs(text):
        if any(keyword in paragraph for keyword in SETUP_KEYWORDS):
            setups.append(truncate_text(paragraph, 90))
    return sorted_unique(setups)


def build_chapter_summary(chapter: ParsedChapter) -> str:
    """Build a short placeholder summary from the chapter body."""

    paragraphs = split_body_paragraphs(chapter.text)
    if not paragraphs:
        return chapter.title
    return truncate_text(paragraphs[0], 80)


def build_entities(prefix: str, entity_sources: dict[str, set[str]]) -> list[ExtractedEntity]:
    """Build stable ordered entities from name to source chapter mapping."""

    entities = []
    for index, name in enumerate(sorted(entity_sources), start=1):
        entities.append(
            ExtractedEntity(
                id=f"{prefix}_{index:03d}",
                name=name,
                source_chapters=sorted(entity_sources[name]),
            )
        )
    return entities


def split_body_paragraphs(text: str) -> list[str]:
    """Split chapter text into body paragraphs without the title line."""

    lines = text.strip().splitlines()
    body = "\n".join(lines[1:]).strip() if lines else ""
    return [
        " ".join(paragraph.split()) for paragraph in re.split(r"\n\s*\n", body) if paragraph.strip()
    ]


def sorted_unique(values: list[str]) -> list[str]:
    """Return values in first-seen order with duplicates removed."""

    seen = set()
    unique = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def has_bad_location_substring(location: str) -> bool:
    """Return whether a candidate location is actually narrative text."""

    return any(substring in location for substring in LOCATION_BAD_SUBSTRINGS)


def truncate_text(text: str, max_length: int) -> str:
    """Truncate text without adding noise for short strings."""

    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1]}…"


def write_entity_analysis_outputs(analysis: EntityAnalysis, output_dir: Path) -> None:
    """Write chapter analysis and entity registry YAML files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    write_chapter_analysis_yaml(analysis.chapter_analyses, output_dir / "chapter_analysis.yaml")
    write_entity_registry_yaml("characters", analysis.characters, output_dir / "characters.yaml")
    write_entity_registry_yaml("locations", analysis.locations, output_dir / "locations.yaml")


def write_chapter_analysis_yaml(analyses: list[ChapterAnalysis], output_path: Path) -> None:
    """Write chapter analyses to YAML."""

    lines = ["chapter_analyses:"]
    for analysis in analyses:
        lines.extend(
            [
                f"  - chapter_id: {quote_yaml_scalar(analysis.chapter_id)}",
                f"    summary: {quote_yaml_scalar(analysis.summary)}",
                "    characters:",
            ]
        )
        lines.extend(f"      - {quote_yaml_scalar(name)}" for name in analysis.characters)
        lines.append("    locations:")
        lines.extend(f"      - {quote_yaml_scalar(name)}" for name in analysis.locations)
        lines.append("    events:")
        for event in analysis.events:
            lines.extend(
                [
                    f"      - id: {quote_yaml_scalar(event.id)}",
                    f"        summary: {quote_yaml_scalar(event.summary)}",
                ]
            )
        lines.append("    possible_setups:")
        for setup in analysis.possible_setups:
            lines.append(f"      - summary: {quote_yaml_scalar(setup.summary)}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_entity_registry_yaml(
    key: str, entities: list[ExtractedEntity], output_path: Path
) -> None:
    """Write a normalized entity registry to YAML."""

    lines = [f"{key}:"]
    for entity in entities:
        lines.extend(
            [
                f"  - id: {quote_yaml_scalar(entity.id)}",
                f"    name: {quote_yaml_scalar(entity.name)}",
                "    source_chapters:",
            ]
        )
        lines.extend(
            f"      - {quote_yaml_scalar(chapter_id)}" for chapter_id in entity.source_chapters
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
