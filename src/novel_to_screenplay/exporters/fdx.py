"""Render a screenplay document as Final Draft (.fdx).

FDX is Final Draft's XML interchange format and the de-facto professional
standard: the file opens directly in Final Draft, WriterDuet, Fade In,
Highland, Celtx and most other screenwriting tools. We emit the documented
``FinalDraft > Content > Paragraph[Type] > Text`` structure so the export is
portable.

Built on ElementTree so every value is XML-escaped and the output is always
well-formed, regardless of what characters a name or line contains.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'

# Final Draft has no Chinese keyword convention; the Type="Scene Heading"
# attribute is what marks the slugline, so the text can read naturally.
LOCATION_MODES = {"INT": "内", "EXT": "外", "INT_EXT": "内外"}
TIME_OF_DAY = {
    "DAY": "日",
    "NIGHT": "夜",
    "MORNING": "晨",
    "EVENING": "黄昏",
    "CONTINUOUS": "连续",
    "LATER": "稍后",
}


def to_fdx(document: dict[str, Any]) -> str:
    """Convert a screenplay_yaml document into a Final Draft (.fdx) string."""

    root = ET.Element(
        "FinalDraft",
        {"DocumentType": "Script", "Template": "No", "Version": "3"},
    )
    content = ET.SubElement(root, "Content")
    for scene in _scenes(document):
        _append_scene(content, scene)
    _append_title_page(root, document)

    ET.indent(root, space="  ")
    return _XML_DECLARATION + ET.tostring(root, encoding="unicode") + "\n"


def write_fdx(document: dict[str, Any], output_path: Path) -> None:
    """Write the screenplay document as an .fdx file at output_path."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(to_fdx(document), encoding="utf-8")


def _paragraph(parent: ET.Element, paragraph_type: str, text: str) -> None:
    para = ET.SubElement(parent, "Paragraph", {"Type": paragraph_type})
    ET.SubElement(para, "Text").text = text


def _append_scene(content: ET.Element, scene: dict[str, Any]) -> None:
    _paragraph(content, "Scene Heading", _scene_heading(scene))
    for element in _script(scene):
        _append_element(content, element)


def _scene_heading(scene: dict[str, Any]) -> str:
    heading = scene.get("scene_heading", {})
    heading = heading if isinstance(heading, dict) else {}
    display = str(heading.get("display", "未知地点")).strip() or "未知地点"
    mode = LOCATION_MODES.get(heading.get("location_mode", ""))
    time = TIME_OF_DAY.get(heading.get("time_of_day", ""))
    location = f"{mode} {display}" if mode else display
    return f"{location} - {time}" if time else location


def _append_element(content: ET.Element, element: dict[str, Any]) -> None:
    element_type = element.get("type")
    text = str(element.get("text", "")).strip()
    if not text:
        return

    if element_type in {"dialogue", "voiceover"}:
        name = str(element.get("character_name", "")).strip()
        if not name:
            _paragraph(content, "Action", text)
            return
        _paragraph(content, "Character", f"{name}（V.O.）" if element_type == "voiceover" else name)
        parenthetical = element.get("parenthetical")
        if isinstance(parenthetical, str) and parenthetical.strip():
            _paragraph(content, "Parenthetical", f"（{parenthetical.strip()}）")
        _paragraph(content, "Dialogue", text)
        subtext = element.get("subtext")
        if isinstance(subtext, str) and subtext.strip():
            # FDX has no subtext concept; keep it as a clearly-marked beat
            # rather than dropping the annotation.
            _paragraph(content, "Action", f"（潜台词：{subtext.strip()}）")
        return

    if element_type == "transition":
        _paragraph(content, "Transition", text)
        return
    _paragraph(content, "Action", text)


def _append_title_page(root: ET.Element, document: dict[str, Any]) -> None:
    metadata = document.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    title = str(metadata.get("title", "")).strip()
    author = str(metadata.get("author", "")).strip()
    if not title and not author:
        return
    content = ET.SubElement(ET.SubElement(root, "TitlePage"), "Content")
    if title:
        _paragraph(content, "Action", title)
    if author:
        _paragraph(content, "Action", f"编剧：{author}")


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
