"""Scene outline generation (rule-based and LLM-based)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from novel_to_screenplay.pipeline.chapter_parser import quote_yaml_scalar
from novel_to_screenplay.pipeline.entity_analyzer import ChapterAnalysis, EntityAnalysis
from novel_to_screenplay.providers import ChatMessage, MockProvider
from novel_to_screenplay.structured_output import StructuredOutputError, complete_json

LOCATION_MODES = {"INT", "EXT", "INT_EXT", "UNKNOWN"}
TIMES_OF_DAY = {"DAY", "NIGHT", "MORNING", "EVENING", "CONTINUOUS", "LATER", "UNKNOWN"}

PRIMARY_LOCATION_PRIORITY = [
    "档案室",
    "地下药品库",
    "药品库",
    "住院楼天台",
    "天台",
    "楼梯间",
    "医院旧楼",
    "旧楼",
    "医院",
]


@dataclass(frozen=True)
class SceneHeading:
    """Minimal scene heading for an outline scene."""

    location_mode: str
    location_id: str | None
    display: str
    time_of_day: str


@dataclass(frozen=True)
class OutlineScene:
    """A generated scene outline item."""

    id: str
    order: int
    chapter_refs: list[str]
    scene_heading: SceneHeading
    summary: str
    dramatic_function: str
    characters_present: list[str]
    required_events: list[str]
    setup_notes: list[str]


@dataclass(frozen=True)
class SceneOutline:
    """Scene outline generated from chapter analysis."""

    scenes: list[OutlineScene]


def build_scene_outline(analysis: EntityAnalysis) -> SceneOutline:
    """Build a first-pass one-scene-per-chapter outline."""

    character_ids_by_name = {character.name: character.id for character in analysis.characters}
    location_ids_by_name = {location.name: location.id for location in analysis.locations}
    scene_count = len(analysis.chapter_analyses)

    scenes = [
        build_scene_from_chapter_analysis(
            chapter_analysis=chapter_analysis,
            index=index,
            scene_count=scene_count,
            character_ids_by_name=character_ids_by_name,
            location_ids_by_name=location_ids_by_name,
        )
        for index, chapter_analysis in enumerate(analysis.chapter_analyses, start=1)
    ]
    return SceneOutline(scenes=scenes)


def build_scene_outline_auto(
    analysis: EntityAnalysis,
    provider: Any,
    *,
    adaptation: dict[str, Any] | None = None,
) -> SceneOutline:
    """Build the outline with the LLM provider, falling back to rules for mock."""

    if provider is None or isinstance(provider, MockProvider):
        return build_scene_outline(analysis)
    return build_scene_outline_with_llm(analysis, provider, adaptation=adaptation)


def build_scene_outline_with_llm(
    analysis: EntityAnalysis,
    provider: Any,
    *,
    max_tokens: int = 2048,
    adaptation: dict[str, Any] | None = None,
) -> SceneOutline:
    """Generate a scene outline with an LLM, validating every id it returns.

    The model may split a chapter into several scenes or merge chapters, but
    all chapter, character, location, and event references are checked against
    the analysis so downstream id integrity holds. The ``adaptation`` hint
    (target_format, pacing) steers how densely chapters are split into scenes.
    If the model returns nothing usable, the rule-based outline is used as a
    fallback.
    """

    valid_chapter_ids = {chapter.chapter_id for chapter in analysis.chapter_analyses}
    valid_character_ids = {character.id for character in analysis.characters}
    valid_location_ids = {location.id for location in analysis.locations}
    location_names_by_id = {location.id: location.name for location in analysis.locations}
    valid_event_ids = {
        event.id for chapter in analysis.chapter_analyses for event in chapter.events
    }

    try:
        raw_scenes = complete_json(
            provider,
            build_outline_prompt(analysis, adaptation),
            expect="array",
            temperature=0.3,
            max_tokens=max_tokens,
        )
    except StructuredOutputError:
        # The model returned nothing parseable even after a repair attempt;
        # fall back to the deterministic rule-based outline as promised.
        return build_scene_outline(analysis)

    scenes: list[OutlineScene] = []
    order = 1
    for raw_scene in raw_scenes:
        if not isinstance(raw_scene, dict):
            continue
        chapter_refs = [
            chapter_id
            for chapter_id in as_str_list(raw_scene.get("chapter_refs"))
            if chapter_id in valid_chapter_ids
        ]
        summary = raw_scene.get("summary")
        if not chapter_refs or not isinstance(summary, str) or not summary.strip():
            continue

        location_id = raw_scene.get("location_id")
        if location_id not in valid_location_ids:
            location_id = None
        display = raw_scene.get("display")
        if not isinstance(display, str) or not display.strip():
            display = location_names_by_id.get(location_id, "未知地点")

        scenes.append(
            OutlineScene(
                id=f"sc_{order:03d}",
                order=order,
                chapter_refs=chapter_refs,
                scene_heading=SceneHeading(
                    location_mode=normalize_enum(raw_scene.get("location_mode"), LOCATION_MODES),
                    location_id=location_id,
                    display=display.strip(),
                    time_of_day=normalize_enum(raw_scene.get("time_of_day"), TIMES_OF_DAY),
                ),
                summary=summary.strip(),
                dramatic_function=normalize_dramatic_function(raw_scene.get("dramatic_function")),
                characters_present=[
                    character_id
                    for character_id in as_str_list(raw_scene.get("characters_present"))
                    if character_id in valid_character_ids
                ],
                required_events=[
                    event_id
                    for event_id in as_str_list(raw_scene.get("required_event_ids"))
                    if event_id in valid_event_ids
                ],
                setup_notes=as_str_list(raw_scene.get("setup_notes")),
            )
        )
        order += 1

    if not scenes:
        return build_scene_outline(analysis)
    return SceneOutline(scenes=scenes)


def build_outline_prompt(
    analysis: EntityAnalysis,
    adaptation: dict[str, Any] | None = None,
) -> list[ChatMessage]:
    """Build the provider prompt for outline generation."""

    character_ids_by_name = {character.name: character.id for character in analysis.characters}
    location_ids_by_name = {location.name: location.id for location in analysis.locations}
    chapters_payload = [
        {
            "chapter_id": chapter.chapter_id,
            "summary": chapter.summary,
            "character_ids": [
                character_ids_by_name[name]
                for name in chapter.characters
                if name in character_ids_by_name
            ],
            "location_ids": [
                location_ids_by_name[name]
                for name in chapter.locations
                if name in location_ids_by_name
            ],
            "events": [{"id": event.id, "summary": event.summary} for event in chapter.events],
            "possible_setups": [setup.summary for setup in chapter.possible_setups],
        }
        for chapter in analysis.chapter_analyses
    ]
    payload = {
        "adaptation": {
            "target_format": (adaptation or {}).get("target_format", "screenplay"),
            "pacing": (adaptation or {}).get("pacing", "balanced"),
        },
        "characters": [
            {"id": character.id, "name": character.name} for character in analysis.characters
        ],
        "locations": [
            {"id": location.id, "name": location.name} for location in analysis.locations
        ],
        "chapters": chapters_payload,
        "output_contract": [
            {
                "chapter_refs": ["来自 chapters 的 chapter_id，至少一个"],
                "location_id": "来自 locations 的 id，可省略",
                "display": "场景地点显示名",
                "location_mode": "INT | EXT | INT_EXT | UNKNOWN",
                "time_of_day": "DAY | NIGHT | MORNING | EVENING | CONTINUOUS | LATER | UNKNOWN",
                "summary": "本场一句话剧情",
                "dramatic_function": "如 inciting_incident、development、payoff",
                "characters_present": ["来自 characters 的 id"],
                "required_event_ids": ["来自对应章节 events 的 id"],
                "setup_notes": ["与本场相关的伏笔说明，可为空"],
            }
        ],
    }
    return [
        ChatMessage(
            role="system",
            content=(
                "你是专业的中文剧本结构师。请基于章节分析规划场景顺序，"
                "一章可拆成多场或多章合并为一场。"
                "请按 adaptation 控制分场密度：pacing 为 fast/compressed 时倾向合并、减少场次，"
                "slow_burn 时倾向拆分、增加场次；target_format 为 microdrama_episode 时"
                "倾向多个短场。"
                "只返回 JSON 数组，每个元素符合 output_contract，不要 Markdown，不要解释。"
                "所有 id 必须来自输入，不要编造。"
            ),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
        ),
    ]


def as_str_list(value: Any) -> list[str]:
    """Coerce a provider value into a list of non-empty strings."""

    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if isinstance(item, str) and item.strip():
            items.append(item.strip())
    return items


def normalize_enum(value: Any, allowed: set[str]) -> str:
    """Return an uppercased value when it is in the allowed set, else UNKNOWN."""

    if isinstance(value, str) and value.strip().upper() in allowed:
        return value.strip().upper()
    return "UNKNOWN"


def normalize_dramatic_function(value: Any) -> str:
    """Normalize the dramatic function label."""

    if isinstance(value, str) and value.strip():
        return value.strip()
    return "development"


def build_scene_from_chapter_analysis(
    chapter_analysis: ChapterAnalysis,
    index: int,
    scene_count: int,
    character_ids_by_name: dict[str, str],
    location_ids_by_name: dict[str, str],
) -> OutlineScene:
    """Convert one chapter analysis into one outline scene."""

    location_name = select_primary_location(chapter_analysis.locations, chapter_analysis.summary)
    location_id = location_ids_by_name.get(location_name)

    return OutlineScene(
        id=f"sc_{index:03d}",
        order=index,
        chapter_refs=[chapter_analysis.chapter_id],
        scene_heading=SceneHeading(
            location_mode=infer_location_mode(location_name),
            location_id=location_id,
            display=location_name,
            time_of_day="UNKNOWN",
        ),
        summary=chapter_analysis.summary,
        dramatic_function=infer_dramatic_function(index, scene_count),
        characters_present=[
            character_ids_by_name[name]
            for name in chapter_analysis.characters
            if name in character_ids_by_name
        ],
        required_events=[event.id for event in chapter_analysis.events],
        setup_notes=[setup.summary for setup in chapter_analysis.possible_setups],
    )


def infer_dramatic_function(index: int, scene_count: int) -> str:
    """Infer a coarse dramatic function from scene position."""

    if index == 1:
        return "inciting_incident"
    if index == scene_count:
        return "payoff"
    return "development"


def select_primary_location(locations: list[str], summary: str = "") -> str:
    """Select the most useful location for a scene heading."""

    if not locations:
        return "未知地点"
    summary_locations = [location for location in locations if location in summary]
    if summary_locations:
        return select_by_priority(summary_locations)
    return select_by_priority(locations)


def select_by_priority(locations: list[str]) -> str:
    """Select the first location matching the priority list."""

    for priority in PRIMARY_LOCATION_PRIORITY:
        for location in locations:
            if priority in location:
                return location
    return locations[0]


def infer_location_mode(location_name: str) -> str:
    """Infer INT/EXT mode from simple location names."""

    if any(keyword in location_name for keyword in ("天台", "旧楼", "医院")):
        return "EXT"
    if any(keyword in location_name for keyword in ("档案室", "药品库", "楼梯间")):
        return "INT"
    return "UNKNOWN"


def write_scene_outline_yaml(outline: SceneOutline, output_path: Path) -> None:
    """Write scene outline YAML."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["scenes:"]
    for scene in outline.scenes:
        lines.extend(
            [
                f"  - id: {quote_yaml_scalar(scene.id)}",
                f"    order: {scene.order}",
                "    chapter_refs:",
            ]
        )
        lines.extend(
            f"      - {quote_yaml_scalar(chapter_id)}" for chapter_id in scene.chapter_refs
        )
        lines.extend(
            [
                "    scene_heading:",
                f"      location_mode: {quote_yaml_scalar(scene.scene_heading.location_mode)}",
            ]
        )
        if scene.scene_heading.location_id:
            lines.append(f"      location_id: {quote_yaml_scalar(scene.scene_heading.location_id)}")
        lines.extend(
            [
                f"      display: {quote_yaml_scalar(scene.scene_heading.display)}",
                f"      time_of_day: {quote_yaml_scalar(scene.scene_heading.time_of_day)}",
                f"    summary: {quote_yaml_scalar(scene.summary)}",
                f"    dramatic_function: {quote_yaml_scalar(scene.dramatic_function)}",
                "    characters_present:",
            ]
        )
        lines.extend(
            f"      - {quote_yaml_scalar(character_id)}"
            for character_id in scene.characters_present
        )
        lines.append("    required_events:")
        lines.extend(f"      - {quote_yaml_scalar(event_id)}" for event_id in scene.required_events)
        lines.append("    setup_notes:")
        lines.extend(f"      - {quote_yaml_scalar(note)}" for note in scene.setup_notes)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
