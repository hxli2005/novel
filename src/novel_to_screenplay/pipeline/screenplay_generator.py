"""Rule-based screenplay YAML document generation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from novel_to_screenplay import __version__
from novel_to_screenplay.pipeline.chapter_parser import ParsedChapter, quote_yaml_scalar
from novel_to_screenplay.pipeline.entity_analyzer import (
    SETUP_KEYWORDS,
    EntityAnalysis,
    ExtractedEntity,
)
from novel_to_screenplay.pipeline.scene_outliner import OutlineScene, SceneOutline

SCHEMA_VERSION = "screenplay_yaml/v0.1"


@dataclass(frozen=True)
class ScreenplayGenerationOptions:
    """User-editable metadata for the generated screenplay."""

    title: str = "剧本初稿"
    author: str = "待填写"
    language: str = "zh-CN"
    created_at: str | None = None
    target_format: str = "screenplay"
    fidelity: str = "balanced"
    pacing: str = "compressed"
    target_runtime_min: int = 8


def build_screenplay_document(
    chapters: list[ParsedChapter],
    analysis: EntityAnalysis,
    outline: SceneOutline,
    options: ScreenplayGenerationOptions | None = None,
) -> dict[str, Any]:
    """Build a complete screenplay_yaml/v0.1 document from pipeline outputs."""

    options = options or ScreenplayGenerationOptions()
    chapter_summaries = {
        chapter_analysis.chapter_id: chapter_analysis.summary
        for chapter_analysis in analysis.chapter_analyses
    }
    characters_by_id = {character.id: character for character in analysis.characters}
    locations_by_id = {location.id: location for location in analysis.locations}
    scene_ids_by_chapter = build_scene_ids_by_chapter(outline.scenes)

    return {
        "schema_version": SCHEMA_VERSION,
        "metadata": build_metadata(options),
        "source": build_source(chapters, options.title, chapter_summaries),
        "adaptation": build_adaptation(options),
        "story_world": build_story_world(options.title, chapter_summaries, analysis.locations),
        "characters": build_characters(analysis.characters, outline.scenes),
        "locations": build_locations(analysis.locations, outline.scenes),
        "structure": build_structure(analysis, outline.scenes),
        "scenes": [
            build_screenplay_scene(scene, index, outline.scenes, characters_by_id, locations_by_id)
            for index, scene in enumerate(outline.scenes)
        ],
        "quality_report": build_quality_report(chapters, scene_ids_by_chapter),
    }


def build_metadata(options: ScreenplayGenerationOptions) -> dict[str, Any]:
    """Build document metadata."""

    created_at = options.created_at or datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "title": options.title,
        "author": options.author,
        "language": options.language,
        "created_at": created_at,
        "generator": {
            "name": "novel-to-screenplay",
            "version": __version__,
        },
        "rights": {
            "source_copyright_owner": options.author,
            "adaptation_notes": "AI 辅助生成的可编辑剧本初稿，需作者复核和打磨。",
        },
    }


def build_source(
    chapters: list[ParsedChapter],
    original_title: str,
    chapter_summaries: Mapping[str, str],
) -> dict[str, Any]:
    """Build source novel metadata."""

    return {
        "source_type": "novel",
        "original_title": original_title,
        "chapter_count": len(chapters),
        "chapters": [
            {
                "id": chapter.id,
                "order": chapter.order,
                "title": chapter.title,
                "word_count": chapter.word_count,
                "text_hash": chapter.text_hash,
                "summary": chapter_summaries.get(chapter.id) or chapter.summary or chapter.title,
            }
            for chapter in chapters
        ],
    }


def build_adaptation(options: ScreenplayGenerationOptions) -> dict[str, Any]:
    """Build adaptation settings for the first draft from user options."""

    return {
        "target_format": options.target_format,
        "target_runtime_min": options.target_runtime_min,
        "episode": {
            "mode": "single",
            "number": None,
        },
        "strategy": {
            "fidelity": options.fidelity,
            "pacing": options.pacing,
            "dialogue_style": "natural",
            "narration_policy": "convert_to_action_or_dialogue",
        },
        "assumptions": [
            "第一版采用规则型生成器，将每章改编为一个主要场景。",
            "心理描写和叙述性文字会先转成动作、场记或待改写提示。",
        ],
        "human_review_required": True,
    }


def build_story_world(
    title: str,
    chapter_summaries: Mapping[str, str],
    locations: list[ExtractedEntity],
) -> dict[str, Any]:
    """Build a compact story-world summary."""

    ordered_summaries = [summary for _, summary in sorted(chapter_summaries.items()) if summary]
    primary_places = [location.name for location in locations[:3]]
    logline_summary = ordered_summaries[0] if ordered_summaries else "待作者补充一句话梗概。"
    synopsis = " ".join(ordered_summaries) if ordered_summaries else "待作者补充完整剧情摘要。"
    return {
        "logline": f"{title}：{logline_summary}",
        "synopsis": synopsis,
        "themes": [],
        "setting": {
            "time_period": "待确认",
            "primary_places": primary_places,
        },
        "timeline_notes": ["当前时间线按章节顺序整理，需作者复核闪回、伏笔和跨章因果关系。"],
    }


def build_characters(
    characters: list[ExtractedEntity],
    scenes: list[OutlineScene],
) -> list[dict[str, Any]]:
    """Build screenplay character records."""

    protagonist_id = find_first_character_id(scenes)
    return [
        {
            "id": character.id,
            "name": character.name,
            "aliases": [],
            "role": "protagonist" if character.id == protagonist_id else "unknown",
            "age": None,
            "description": f"{character.name}，由小说文本初步抽取的人物。",
            "motivation": "待作者补充。",
            "arc": "待作者补充。",
            "voice": "待作者补充。",
            "first_appearance": {
                "chapter_id": character.source_chapters[0],
            },
            "source_refs": [
                {
                    "chapter_id": chapter_id,
                    "note": "人物名在原文章节中出现。",
                }
                for chapter_id in character.source_chapters
            ],
        }
        for character in characters
    ]


def build_locations(
    locations: list[ExtractedEntity],
    scenes: list[OutlineScene],
) -> list[dict[str, Any]]:
    """Build screenplay location records."""

    mode_by_location_id = {
        scene.scene_heading.location_id: scene.scene_heading.location_mode
        for scene in scenes
        if scene.scene_heading.location_id
    }
    return [
        {
            "id": location.id,
            "name": location.name,
            "type": map_location_type(mode_by_location_id.get(location.id, "UNKNOWN")),
            "visual_description": f"{location.name}，需作者补充更具体的视觉细节。",
            "recurring": len(location.source_chapters) > 1,
            "source_refs": [
                {
                    "chapter_id": chapter_id,
                    "note": "地点名在原文章节中出现。",
                }
                for chapter_id in location.source_chapters
            ],
        }
        for location in locations
    ]


def build_structure(analysis: EntityAnalysis, scenes: list[OutlineScene]) -> dict[str, Any]:
    """Build act and event structure for the generated draft."""

    key_events = []
    chapter_to_scene = {
        chapter_id: scene.id for scene in scenes for chapter_id in scene.chapter_refs
    }
    events = [
        (chapter_analysis.chapter_id, event)
        for chapter_analysis in analysis.chapter_analyses
        for event in chapter_analysis.events
    ]
    for index, (chapter_id, event) in enumerate(events):
        next_event_id = events[index + 1][1].id if index + 1 < len(events) else None
        key_events.append(
            {
                "id": event.id,
                "summary": event.summary,
                "chapter_refs": [chapter_id],
                "scene_ids": [chapter_to_scene[chapter_id]],
                "causal_links": [next_event_id] if next_event_id else [],
            }
        )

    return {
        "acts": [
            {
                "id": f"act_{scene.order:03d}",
                "title": f"第 {scene.order} 场结构段",
                "scene_ids": [scene.id],
            }
            for scene in scenes
        ],
        "key_events": key_events,
        "omitted_material": [],
    }


def build_screenplay_scene(
    scene: OutlineScene,
    scene_index: int,
    all_scenes: list[OutlineScene],
    characters_by_id: Mapping[str, ExtractedEntity],
    locations_by_id: Mapping[str, ExtractedEntity],
) -> dict[str, Any]:
    """Build a full screenplay scene from an outline scene."""

    scene_heading = {
        "location_mode": scene.scene_heading.location_mode,
        "display": scene.scene_heading.display,
        "time_of_day": scene.scene_heading.time_of_day,
    }
    if scene.scene_heading.location_id:
        scene_heading["location_id"] = scene.scene_heading.location_id

    first_character_id = scene.characters_present[0] if scene.characters_present else None
    script = build_script_elements(scene, characters_by_id)

    return {
        "id": scene.id,
        "order": scene.order,
        "chapter_refs": scene.chapter_refs,
        "scene_heading": scene_heading,
        "summary": scene.summary,
        "dramatic_function": scene.dramatic_function,
        "estimated_screen_time_sec": max(60, len(script) * 30),
        "characters_present": scene.characters_present,
        "props": extract_props(scene.setup_notes),
        "beats": build_beats(scene),
        "script": script,
        "continuity": {
            "previous_scene_id": all_scenes[scene_index - 1].id if scene_index > 0 else None,
            "next_scene_id": all_scenes[scene_index + 1].id
            if scene_index + 1 < len(all_scenes)
            else None,
            "open_questions": build_open_questions(scene, first_character_id, locations_by_id),
        },
        "revision_status": "ai_draft",
    }


def build_script_elements(
    scene: OutlineScene,
    characters_by_id: Mapping[str, ExtractedEntity],
) -> list[dict[str, Any]]:
    """Build simple action/dialogue/note script elements for a scene."""

    source_refs = [
        {
            "chapter_id": chapter_id,
            "note": "由章节摘要和场景大纲改写。",
        }
        for chapter_id in scene.chapter_refs
    ]
    script: list[dict[str, Any]] = [
        {
            "type": "action",
            "text": f"{scene.scene_heading.display}。{scene.summary}",
            "source_refs": source_refs,
        }
    ]
    character_id = scene.characters_present[0] if scene.characters_present else None
    character = characters_by_id.get(character_id) if character_id else None
    if character:
        script.append(
            {
                "type": "dialogue",
                "character_id": character.id,
                "character_name": character.name,
                "parenthetical": "压低声音",
                "text": "这条线索不能断。",
                "subtext": "规则型初稿对白，需作者按人物口吻改写。",
                "source_refs": source_refs,
            }
        )
    script.append(
        {
            "type": "note",
            "text": "本场为结构化初稿，请补充具体调度、对白节奏和人物潜台词。",
            "source_refs": source_refs,
        }
    )
    return script


def build_beats(scene: OutlineScene) -> list[dict[str, Any]]:
    """Build scene beats from required events."""

    if not scene.required_events:
        return [
            {
                "id": f"beat_{scene.order:03d}_001",
                "summary": scene.summary,
                "source_refs": build_scene_source_refs(scene),
            }
        ]
    return [
        {
            "id": f"beat_{scene.order:03d}_{index:03d}",
            "summary": f"承接事件 {event_id}。",
            "source_refs": build_scene_source_refs(scene),
        }
        for index, event_id in enumerate(scene.required_events, start=1)
    ]


def build_quality_report(
    chapters: list[ParsedChapter],
    scene_ids_by_chapter: Mapping[str, list[str]],
) -> dict[str, Any]:
    """Build a conservative quality report for the generated draft."""

    return {
        "validation_status": "warning",
        "chapter_coverage": [
            {
                "chapter_id": chapter.id,
                "used_in_scene_ids": scene_ids_by_chapter.get(chapter.id, []),
                "coverage_note": "已映射到至少一个场景，需人工复核删改比例。",
            }
            for chapter in chapters
        ],
        "warnings": [
            {
                "code": "RULE_BASED_DRAFT",
                "message": "当前剧本由规则型生成器组装，精彩度、对白和人物弧光需作者继续打磨。",
            }
        ],
        "unresolved_questions": [
            "跨章伏笔、人物动机和反转铺垫尚未经过长上下文一致性校验。",
        ],
    }


def build_scene_ids_by_chapter(scenes: Iterable[OutlineScene]) -> dict[str, list[str]]:
    """Return scene IDs grouped by source chapter ID."""

    grouped: dict[str, list[str]] = {}
    for scene in scenes:
        for chapter_id in scene.chapter_refs:
            grouped.setdefault(chapter_id, []).append(scene.id)
    return grouped


def build_scene_source_refs(scene: OutlineScene) -> list[dict[str, str]]:
    """Build source references for a scene."""

    return [
        {
            "chapter_id": chapter_id,
            "note": "对应场景大纲引用章节。",
        }
        for chapter_id in scene.chapter_refs
    ]


def build_open_questions(
    scene: OutlineScene,
    first_character_id: str | None,
    locations_by_id: Mapping[str, ExtractedEntity],
) -> list[str]:
    """Build scene-level review questions."""

    questions = []
    if first_character_id is None:
        questions.append("本场未抽取到明确出场人物，需作者确认人物调度。")
    if scene.scene_heading.location_id is None:
        questions.append("本场地点未能匹配地点表 ID，需作者确认场景标题。")
    elif scene.scene_heading.location_id not in locations_by_id:
        questions.append("本场地点 ID 不在地点表中，需校验实体抽取结果。")
    if scene.setup_notes:
        questions.append("本场包含伏笔或线索，需确认后续是否回收。")
    return questions


def find_first_character_id(scenes: list[OutlineScene]) -> str | None:
    """Return the first character ID that appears in scene order."""

    for scene in scenes:
        if scene.characters_present:
            return scene.characters_present[0]
    return None


def map_location_type(location_mode: str) -> str:
    """Map scene heading INT/EXT values to schema location types."""

    return {
        "INT": "interior",
        "EXT": "exterior",
        "INT_EXT": "interior_exterior",
    }.get(location_mode, "unknown")


def extract_props(notes: list[str]) -> list[str]:
    """Extract simple prop names from setup notes."""

    props = []
    for note in notes:
        for keyword in SETUP_KEYWORDS:
            if keyword in note and keyword not in props:
                props.append(keyword)
    return props


def write_screenplay_yaml(document: Mapping[str, Any], output_path: Path) -> None:
    """Write a screenplay YAML document."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dump_yaml(document), encoding="utf-8")


def dump_yaml(value: Mapping[str, Any]) -> str:
    """Dump a limited JSON-like object to readable YAML."""

    return "\n".join(iter_yaml_lines(value, 0)) + "\n"


def iter_yaml_lines(value: Any, indent: int) -> list[str]:
    """Render supported Python values as YAML lines."""

    prefix = " " * indent
    if isinstance(value, Mapping):
        lines = []
        for key, item in value.items():
            if is_scalar(item):
                lines.append(f"{prefix}{key}: {format_scalar(item)}")
            elif is_empty_sequence(item):
                lines.append(f"{prefix}{key}: []")
            elif item == {}:
                lines.append(f"{prefix}{key}: {{}}")
            else:
                lines.append(f"{prefix}{key}:")
                lines.extend(iter_yaml_lines(item, indent + 2))
        return lines
    if isinstance(value, Sequence) and not isinstance(value, str):
        lines = []
        for item in value:
            if is_scalar(item):
                lines.append(f"{prefix}- {format_scalar(item)}")
            elif is_empty_sequence(item):
                lines.append(f"{prefix}- []")
            elif item == {}:
                lines.append(f"{prefix}- {{}}")
            else:
                rendered = iter_yaml_lines(item, indent + 2)
                first_line = rendered[0].lstrip()
                lines.append(f"{prefix}- {first_line}")
                lines.extend(rendered[1:])
        return lines
    return [f"{prefix}{format_scalar(value)}"]


def is_empty_sequence(value: Any) -> bool:
    """Return whether a value is an empty non-string sequence."""

    return isinstance(value, Sequence) and not isinstance(value, str) and not value


def is_scalar(value: Any) -> bool:
    """Return whether a value can be emitted on one YAML line."""

    return value is None or isinstance(value, str | int | float | bool)


def format_scalar(value: Any) -> str:
    """Format a Python scalar for YAML."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return quote_yaml_scalar(str(value))
