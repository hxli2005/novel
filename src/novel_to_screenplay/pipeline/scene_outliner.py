"""Rule-based scene outline generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from novel_to_screenplay.pipeline.chapter_parser import quote_yaml_scalar
from novel_to_screenplay.pipeline.entity_analyzer import ChapterAnalysis, EntityAnalysis

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
