"""LLM-based story-level consistency review.

Where ``consistency`` runs deterministic structural checks, this asks a
provider to read the whole draft and flag higher-order story problems an
author should review: foreshadowing that is never paid off, character arcs
that do not cohere, and cause-and-effect gaps across scenes. It is best-effort
— a malformed model response yields no findings rather than an error.
"""

from __future__ import annotations

import json
from typing import Any

from novel_to_screenplay.pipeline.consistency import ConsistencyFinding
from novel_to_screenplay.providers import ChatMessage
from novel_to_screenplay.structured_output import StructuredOutputError, complete_json

REVIEW_CODES = {"FORESHADOW_UNRESOLVED", "ARC_INCONSISTENCY", "CAUSALITY_GAP"}


def review_story_with_llm(
    document: dict[str, Any],
    provider: Any,
    *,
    max_tokens: int = 1536,
) -> list[ConsistencyFinding]:
    """Ask the provider for story-level findings; return [] if none/unparseable."""

    try:
        raw_findings = complete_json(
            provider,
            build_story_review_prompt(document),
            expect="array",
            temperature=0.2,
            max_tokens=max_tokens,
        )
    except StructuredOutputError:
        return []
    valid_scene_ids = {
        scene["id"]
        for scene in _scenes(document)
        if isinstance(scene.get("id"), str)
    }
    return normalize_review_findings(raw_findings, valid_scene_ids)


def build_story_review_prompt(document: dict[str, Any]) -> list[ChatMessage]:
    """Build a compact whole-story payload for the review prompt."""

    names_by_id = {
        character["id"]: character.get("name", character["id"])
        for character in _characters(document)
        if isinstance(character.get("id"), str)
    }
    payload = {
        "story_world": {
            "logline": document.get("story_world", {}).get("logline", ""),
            "synopsis": document.get("story_world", {}).get("synopsis", ""),
        },
        "characters": [
            {
                "id": character.get("id"),
                "name": character.get("name"),
                "role": character.get("role"),
            }
            for character in _characters(document)
        ],
        "scenes": [
            {
                "id": scene.get("id"),
                "summary": scene.get("summary", ""),
                "dramatic_function": scene.get("dramatic_function", ""),
                "characters_present": [
                    names_by_id.get(character_id, character_id)
                    for character_id in scene.get("characters_present", [])
                    if isinstance(character_id, str)
                ],
                "beats": [
                    beat.get("summary", "")
                    for beat in scene.get("beats", [])
                    if isinstance(beat, dict)
                ],
            }
            for scene in _scenes(document)
        ],
        "output_contract": [
            {
                "code": "FORESHADOW_UNRESOLVED | ARC_INCONSISTENCY | CAUSALITY_GAP",
                "message": "一句话描述需作者复核的问题（中文）",
                "scene_id": "最相关的场景 id，可省略",
            }
        ],
    }
    return [
        ChatMessage(
            role="system",
            content=(
                "你是资深剧本顾问。请通读整部剧本，做故事级一致性复审，找出："
                "伏笔未回收(FORESHADOW_UNRESOLVED)、人物弧光不连贯(ARC_INCONSISTENCY)、"
                "跨场因果断裂(CAUSALITY_GAP)。"
                "只返回 JSON 数组，每个元素含 code、message、可选 scene_id；"
                "code 只能用上述三种。没有问题就返回空数组 []。"
                "不要 Markdown，不要解释。"
            ),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
        ),
    ]


def normalize_review_findings(
    raw_findings: list[Any],
    valid_scene_ids: set[str],
) -> list[ConsistencyFinding]:
    """Validate provider findings into ConsistencyFinding records."""

    findings = []
    for item in raw_findings:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if code not in REVIEW_CODES:
            continue
        message = item.get("message")
        if not isinstance(message, str) or not message.strip():
            continue
        scene_id = item.get("scene_id")
        if not (isinstance(scene_id, str) and scene_id in valid_scene_ids):
            scene_id = None
        findings.append(
            ConsistencyFinding(code=code, message=message.strip(), scene_id=scene_id)
        )
    return findings


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
