"""Rule-based entity and chapter analysis extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from novel_to_screenplay.pipeline.chapter_parser import ParsedChapter, quote_yaml_scalar

MAX_EVENTS_PER_CHAPTER = 3

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
