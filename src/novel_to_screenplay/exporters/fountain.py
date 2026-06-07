"""Render a screenplay document as Fountain (https://fountain.io).

Fountain is the open, plain-text screenplay format that virtually every
modern screenwriting tool (Final Draft, WriterDuet, Highland, Slugline,
Scrivener, ...) can import. Our schema maps onto it almost 1:1. Chinese names
have no upper-case, so character cues and transitions are written with
Fountain's forced markers (`@`, `>`) to stay unambiguous.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

LOCATION_PREFIXES = {
    "INT": "INT.",
    "EXT": "EXT.",
    "INT_EXT": "INT./EXT.",
}
TIME_OF_DAY = {
    "DAY": "日",
    "NIGHT": "夜",
    "MORNING": "晨",
    "EVENING": "黄昏",
    "CONTINUOUS": "连续",
    "LATER": "稍后",
}


def to_fountain(document: dict[str, Any]) -> str:
    """Convert a screenplay_yaml document into a Fountain string."""

    blocks: list[str] = []
    title_page = _title_page(document)
    if title_page:
        blocks.append(title_page)

    for scene in _scenes(document):
        blocks.extend(_render_scene(scene))

    return "\n\n".join(block for block in blocks if block) + "\n"


def write_fountain(document: dict[str, Any], output_path: Path) -> None:
    """Write the screenplay document as a Fountain file at output_path."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(to_fountain(document), encoding="utf-8")


def _title_page(document: dict[str, Any]) -> str:
    metadata = document.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    lines = []
    title = metadata.get("title")
    author = metadata.get("author")
    if isinstance(title, str) and title.strip():
        lines.append(f"Title: {title.strip()}")
    if isinstance(author, str) and author.strip():
        lines.append("Credit: 编剧")
        lines.append(f"Author: {author.strip()}")
    return "\n".join(lines)


def _render_scene(scene: dict[str, Any]) -> list[str]:
    blocks = [_scene_heading(scene)]
    for element in _script(scene):
        rendered = _render_element(element)
        if rendered:
            blocks.append(rendered)
    return blocks


def _scene_heading(scene: dict[str, Any]) -> str:
    heading = scene.get("scene_heading", {})
    heading = heading if isinstance(heading, dict) else {}
    display = str(heading.get("display", "未知地点")).strip() or "未知地点"
    prefix = LOCATION_PREFIXES.get(heading.get("location_mode", ""))
    time = TIME_OF_DAY.get(heading.get("time_of_day", ""))
    location = f"{prefix} {display}" if prefix else f".{display}"
    return f"{location} - {time}" if time else location


def _render_element(element: dict[str, Any]) -> str:
    element_type = element.get("type")
    text = str(element.get("text", "")).strip()
    if not text:
        return ""

    if element_type in {"dialogue", "voiceover"}:
        name = str(element.get("character_name", "")).strip()
        if not name:
            return text
        cue = f"@{name} (V.O.)" if element_type == "voiceover" else f"@{name}"
        lines = [cue]
        parenthetical = element.get("parenthetical")
        if isinstance(parenthetical, str) and parenthetical.strip():
            lines.append(f"({parenthetical.strip()})")
        lines.append(text)
        subtext = element.get("subtext")
        if isinstance(subtext, str) and subtext.strip():
            lines.append(f"[[潜台词：{subtext.strip()}]]")
        return "\n".join(lines)

    if element_type == "transition":
        return f"> {text}"
    if element_type in {"note", "parenthetical"}:
        return f"[[{text}]]"
    return text


def _scenes(document: dict[str, Any]) -> list[dict[str, Any]]:
    scenes = document.get("scenes")
    if not isinstance(scenes, list):
        return []
    return [scene for scene in scenes if isinstance(scene, dict)]


def _script(scene: dict[str, Any]) -> list[dict[str, Any]]:
    script = scene.get("script")
    if not isinstance(script, list):
        return []
    return [element for element in script if isinstance(element, dict)]
