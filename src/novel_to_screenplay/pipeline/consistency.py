"""Deterministic story-level consistency checks over a screenplay document.

These checks read a finished screenplay document and surface issues an author
should review: chapters that never made it into a scene, characters that are
registered but never appear, and characters who appear but never speak. They
are intentionally rule-based so they run offline and are fully reproducible;
LLM-driven checks (foreshadow payoff, arc coherence) can layer on later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DIALOGUE_TYPES = {"dialogue", "voiceover"}
WarningIdentity = tuple[str, str, str | None]


@dataclass(frozen=True)
class ConsistencyFinding:
    """One reviewable consistency issue."""

    code: str
    message: str
    scene_id: str | None = None


def analyze_consistency(document: dict[str, Any]) -> list[ConsistencyFinding]:
    """Run every consistency check over a screenplay document."""

    findings: list[ConsistencyFinding] = []
    findings.extend(check_uncovered_chapters(document))
    findings.extend(check_unused_characters(document))
    findings.extend(check_silent_characters(document))
    return findings


def check_uncovered_chapters(document: dict[str, Any]) -> list[ConsistencyFinding]:
    """Flag source chapters that no scene adapts."""

    used_chapter_ids = {
        chapter_id
        for scene in _scenes(document)
        for chapter_id in _str_list(scene.get("chapter_refs"))
    }
    findings = []
    for chapter in _chapters(document):
        chapter_id = chapter.get("id")
        if isinstance(chapter_id, str) and chapter_id not in used_chapter_ids:
            title = chapter.get("title", chapter_id)
            findings.append(
                ConsistencyFinding(
                    code="CHAPTER_NOT_ADAPTED",
                    message=f"章节 {chapter_id}「{title}」未被任何场景改编，请确认是否遗漏。",
                )
            )
    return findings


def check_unused_characters(document: dict[str, Any]) -> list[ConsistencyFinding]:
    """Flag registered characters that never appear in a scene."""

    present_ids = {
        character_id
        for scene in _scenes(document)
        for character_id in _str_list(scene.get("characters_present"))
    }
    # A character who speaks in a scene is present even if (in a slightly
    # inconsistent but schema-valid document) they are missing from
    # characters_present. Counting speakers avoids a false CHARACTER_UNUSED.
    present_ids |= _speaking_character_ids(document)
    findings = []
    for character in _characters(document):
        character_id = character.get("id")
        if isinstance(character_id, str) and character_id not in present_ids:
            name = character.get("name", character_id)
            message = f"人物 {name}（{character_id}）已登记但未出现在任何场景，建议删除或补戏。"
            findings.append(ConsistencyFinding(code="CHARACTER_UNUSED", message=message))
    return findings


def check_silent_characters(document: dict[str, Any]) -> list[ConsistencyFinding]:
    """Flag characters who are present in a scene but never speak anywhere."""

    speaking_ids = _speaking_character_ids(document)
    first_scene_by_character: dict[str, str | None] = {}
    for scene in _scenes(document):
        scene_id = scene.get("id")
        scene_id = scene_id if isinstance(scene_id, str) else None
        for character_id in _str_list(scene.get("characters_present")):
            first_scene_by_character.setdefault(character_id, scene_id)

    names = {
        character["id"]: character.get("name", character["id"])
        for character in _characters(document)
        if isinstance(character.get("id"), str)
    }
    findings = []
    for character_id in sorted(first_scene_by_character):
        if character_id not in speaking_ids:
            name = names.get(character_id, character_id)
            findings.append(
                ConsistencyFinding(
                    code="CHARACTER_NO_DIALOGUE",
                    message=f"人物 {name}（{character_id}）在场但全程没有台词，请作者复核戏份。",
                    scene_id=first_scene_by_character[character_id],
                )
            )
    return findings


def apply_consistency_findings(
    document: dict[str, Any],
    findings: list[ConsistencyFinding],
) -> dict[str, Any]:
    """Merge findings into the document's quality_report warnings in place."""

    report = document.setdefault("quality_report", {})
    if not isinstance(report, dict):
        report = {}
        document["quality_report"] = report
    warnings = report.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
        report["warnings"] = warnings

    existing_warning_ids = {
        warning_id for warning in warnings if (warning_id := _warning_identity(warning)) is not None
    }
    for finding in findings:
        warning = _finding_to_warning(finding)
        warning_id = _warning_identity(warning)
        if warning_id in existing_warning_ids:
            continue
        warnings.append(warning)
        existing_warning_ids.add(warning_id)

    if findings and report.get("validation_status") == "pass":
        report["validation_status"] = "warning"
    return document


def _finding_to_warning(finding: ConsistencyFinding) -> dict[str, Any]:
    warning: dict[str, Any] = {"code": finding.code, "message": finding.message}
    if finding.scene_id:
        warning["scene_id"] = finding.scene_id
    return warning


def _warning_identity(warning: Any) -> WarningIdentity | None:
    if not isinstance(warning, dict):
        return None

    code = warning.get("code")
    message = warning.get("message")
    scene_id = warning.get("scene_id")
    if not isinstance(code, str) or not isinstance(message, str):
        return None
    if scene_id is not None and not isinstance(scene_id, str):
        return None
    return (code, message, scene_id)


def _scenes(document: dict[str, Any]) -> list[dict[str, Any]]:
    scenes = document.get("scenes")
    if not isinstance(scenes, list):
        return []
    return [scene for scene in scenes if isinstance(scene, dict)]


def _characters(document: dict[str, Any]) -> list[dict[str, Any]]:
    characters = document.get("characters")
    if not isinstance(characters, list):
        return []
    return [character for character in characters if isinstance(character, dict)]


def _chapters(document: dict[str, Any]) -> list[dict[str, Any]]:
    source = document.get("source")
    chapters = source.get("chapters") if isinstance(source, dict) else None
    if not isinstance(chapters, list):
        return []
    return [chapter for chapter in chapters if isinstance(chapter, dict)]


def _script(scene: dict[str, Any]) -> list[dict[str, Any]]:
    script = scene.get("script")
    if not isinstance(script, list):
        return []
    return [element for element in script if isinstance(element, dict)]


def _speaking_character_ids(document: dict[str, Any]) -> set[str]:
    """Character ids that speak via a dialogue or voiceover element."""

    speaking_ids: set[str] = set()
    for scene in _scenes(document):
        for element in _script(scene):
            if element.get("type") in DIALOGUE_TYPES:
                speaker = element.get("character_id")
                if isinstance(speaker, str):
                    speaking_ids.add(speaker)
    return speaking_ids


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
