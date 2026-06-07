"""AI-assisted scene script drafting."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from novel_to_screenplay.providers import (
    ChatMessage,
    MockProvider,
    ProviderCompletion,
    ProviderError,
)
from novel_to_screenplay.structured_output import StructuredOutputError, extract_json_value

SUPPORTED_SCRIPT_TYPES = {"action", "dialogue", "note", "transition"}


@dataclass(frozen=True)
class SceneDraftResult:
    """Summary of scene drafting changes."""

    document: dict[str, Any]
    drafted_scene_ids: list[str]
    provider: str
    model: str


class SceneDraftError(ProviderError):
    """Raised when a scene cannot be drafted into valid screenplay elements."""


def draft_screenplay_scenes(
    document: dict[str, Any],
    provider: Any,
    *,
    max_tokens: int = 2048,
    scene_limit: int | None = None,
    on_scene: Callable[[int, int, str], None] | None = None,
) -> SceneDraftResult:
    """Draft screenplay script blocks scene by scene.

    ``on_scene(index, total, scene_id)`` is invoked after each scene is drafted
    (1-based index), so callers such as the web UI can report per-scene progress
    during the slowest pipeline stage.
    """

    drafted_document = copy.deepcopy(document)
    scenes = drafted_document.get("scenes", [])
    if not isinstance(scenes, list):
        raise SceneDraftError("screenplay document must contain a scenes list.")

    characters_by_id = build_characters_by_id(drafted_document)
    drafted_scene_ids = []
    provider_name = getattr(provider, "name", "unknown")
    model = getattr(provider, "model", provider_name)

    selected = [scene for scene in scenes[:scene_limit] if isinstance(scene, dict)]
    total = len(selected)
    for index, scene in enumerate(selected, start=1):
        script = draft_scene_script(
            drafted_document,
            scene,
            characters_by_id,
            provider,
            max_tokens=max_tokens,
        )
        scene["script"] = script
        scene["revision_status"] = "ai_drafted"
        drafted_scene_ids.append(str(scene.get("id", "")))
        if on_scene is not None:
            on_scene(index, total, str(scene.get("id", "")))

    add_drafting_warning(drafted_document, provider_name, model, drafted_scene_ids)
    return SceneDraftResult(
        document=drafted_document,
        drafted_scene_ids=drafted_scene_ids,
        provider=provider_name,
        model=str(model),
    )


def draft_scene_script(
    document: dict[str, Any],
    scene: dict[str, Any],
    characters_by_id: dict[str, dict[str, Any]],
    provider: Any,
    *,
    max_tokens: int,
) -> list[dict[str, Any]]:
    """Draft one scene script."""

    if isinstance(provider, MockProvider):
        return build_mock_script(scene, characters_by_id)

    completion = provider.complete(
        build_scene_prompt(document, scene, characters_by_id),
        temperature=0.35,
        max_tokens=max_tokens,
    )
    return normalize_script_elements(
        parse_script_json(completion),
        scene,
        characters_by_id,
    )


def build_scene_prompt(
    document: dict[str, Any],
    scene: dict[str, Any],
    characters_by_id: dict[str, dict[str, Any]],
) -> list[ChatMessage]:
    """Build a provider prompt for one scene."""

    scene_characters = [
        summarize_character(characters_by_id[character_id])
        for character_id in scene.get("characters_present", [])
        if character_id in characters_by_id
    ]
    payload = {
        "adaptation": summarize_adaptation(document),
        "story_world": {
            "logline": document.get("story_world", {}).get("logline", ""),
            "synopsis": document.get("story_world", {}).get("synopsis", ""),
        },
        "scene": {
            "id": scene.get("id"),
            "scene_heading": scene.get("scene_heading", {}),
            "summary": scene.get("summary", ""),
            "dramatic_function": scene.get("dramatic_function", ""),
            "chapter_refs": scene.get("chapter_refs", []),
            "characters_present": scene_characters,
            "props": scene.get("props", []),
            "beats": scene.get("beats", []),
            "continuity": scene.get("continuity", {}),
        },
        "output_contract": [
            {
                "type": "action",
                "text": "可拍摄动作或环境描写",
            },
            {
                "type": "dialogue",
                "character_id": "必须来自 characters_present",
                "character_name": "人物姓名",
                "text": "对白",
                "parenthetical": "可选",
                "subtext": "可选",
            },
            {
                "type": "note",
                "text": "给作者的改写提示，可选",
            },
        ],
    }
    return [
        ChatMessage(
            role="system",
            content=(
                "你是专业中文剧本改编助手。请把小说场景大纲扩写成可编辑剧本片段。"
                "请严格遵循 adaptation：按 target_format 的体裁惯例改写，"
                "fidelity 决定对原著的取舍尺度，pacing 决定节奏与对白密度，"
                "dialogue_style 决定对白风格，narration_policy 决定旁白处理方式。"
                "只返回 JSON 数组，不要 Markdown，不要解释。"
                "数组元素只能使用 action、dialogue、note。"
                "对白的 character_id 必须来自输入 characters_present。"
            ),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
        ),
    ]


def parse_script_json(completion: ProviderCompletion) -> Any:
    """Parse provider completion as a JSON array."""

    try:
        parsed = extract_json_value(completion.text)
    except StructuredOutputError as exc:
        raise SceneDraftError("provider did not return a valid JSON script array.") from exc
    if not isinstance(parsed, list):
        raise SceneDraftError("provider script response must be a JSON array.")
    return parsed


def normalize_script_elements(
    raw_elements: list[Any],
    scene: dict[str, Any],
    characters_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate and normalize provider-generated script elements."""

    if not raw_elements:
        raise SceneDraftError("provider returned an empty script array.")

    normalized = []
    allowed_character_ids = {
        character_id
        for character_id in scene.get("characters_present", [])
        if character_id in characters_by_id
    }
    for index, raw_element in enumerate(raw_elements):
        if not isinstance(raw_element, dict):
            raise SceneDraftError(f"script element {index} must be an object.")
        element_type = raw_element.get("type")
        if element_type not in SUPPORTED_SCRIPT_TYPES:
            raise SceneDraftError(f"unsupported script element type: {element_type}")
        text = raw_element.get("text")
        if not isinstance(text, str) or not text.strip():
            raise SceneDraftError(f"script element {index} must contain non-empty text.")
        if element_type == "dialogue":
            normalized.append(
                normalize_dialogue(raw_element, allowed_character_ids, characters_by_id, scene)
            )
            continue
        element = {
            "type": element_type,
            "text": text.strip(),
        }
        if element_type != "transition":
            element["source_refs"] = normalize_source_refs(raw_element.get("source_refs"), scene)
        normalized.append(element)
    return normalized


def normalize_dialogue(
    raw_element: dict[str, Any],
    allowed_character_ids: set[str],
    characters_by_id: dict[str, dict[str, Any]],
    scene: dict[str, Any],
) -> dict[str, Any]:
    """Normalize a dialogue script element."""

    character_id = raw_element.get("character_id")
    if not isinstance(character_id, str) or character_id not in characters_by_id:
        raise SceneDraftError(f"dialogue references unknown character: {character_id}")
    if character_id not in allowed_character_ids:
        # The model voiced a real character the outliner didn't pre-list for
        # this scene. Accept it and record the character as present so the
        # scene stays internally consistent, rather than failing the run.
        allowed_character_ids.add(character_id)
        present = scene.setdefault("characters_present", [])
        if character_id not in present:
            present.append(character_id)
    character_name = raw_element.get("character_name") or characters_by_id[character_id].get("name")
    if not isinstance(character_name, str) or not character_name.strip():
        raise SceneDraftError(f"dialogue missing character_name for {character_id}")

    element = {
        "type": "dialogue",
        "character_id": character_id,
        "character_name": character_name.strip(),
        "text": raw_element["text"].strip(),
        "source_refs": normalize_source_refs(raw_element.get("source_refs"), scene),
    }
    for optional_key in ("parenthetical", "subtext"):
        value = raw_element.get(optional_key)
        if isinstance(value, str) and value.strip():
            element[optional_key] = value.strip()
    return element


def normalize_source_refs(source_refs: Any, scene: dict[str, Any]) -> list[dict[str, str]]:
    """Normalize source refs or derive them from the scene chapter refs."""

    if isinstance(source_refs, list):
        refs = [
            {
                "chapter_id": str(source_ref["chapter_id"]),
                "note": str(source_ref.get("note", "AI 逐场扩写。")),
            }
            for source_ref in source_refs
            if isinstance(source_ref, dict) and source_ref.get("chapter_id")
        ]
        if refs:
            return refs
    return [
        {
            "chapter_id": str(chapter_id),
            "note": "AI 逐场扩写。",
        }
        for chapter_id in scene.get("chapter_refs", [])
    ]


def build_mock_script(
    scene: dict[str, Any],
    characters_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build deterministic scene script for local tests and demos."""

    source_refs = normalize_source_refs(None, scene)
    display = scene.get("scene_heading", {}).get("display", "场景")
    summary = scene.get("summary", "")
    script: list[dict[str, Any]] = [
        {
            "type": "action",
            "text": f"{display}里，冲突被推进。{summary}",
            "source_refs": source_refs,
        }
    ]
    first_character_id = next(
        (
            character_id
            for character_id in scene.get("characters_present", [])
            if character_id in characters_by_id
        ),
        None,
    )
    if first_character_id:
        script.append(
            {
                "type": "dialogue",
                "character_id": first_character_id,
                "character_name": str(characters_by_id[first_character_id].get("name", "")),
                "text": "我们不能再等了。",
                "subtext": "mock provider 生成的占位对白，真实 provider 会替换为更贴合人物的对白。",
                "source_refs": source_refs,
            }
        )
    script.append(
        {
            "type": "note",
            "text": "本场已通过 provider 扩写，仍需作者复核节奏、潜台词和伏笔回收。",
            "source_refs": source_refs,
        }
    )
    return script


def add_drafting_warning(
    document: dict[str, Any],
    provider_name: str,
    model: str,
    scene_ids: list[str],
) -> None:
    """Append an AI drafting warning to the quality report."""

    quality_report = document.setdefault("quality_report", {})
    warnings = quality_report.setdefault("warnings", [])
    if isinstance(warnings, list):
        warnings.append(
            {
                "code": "AI_SCENE_DRAFTING",
                "message": (
                    f"已使用 {provider_name}/{model} 扩写 {len(scene_ids)} 场，"
                    "需作者复核人物声音、剧情连续性和伏笔回收。"
                ),
            }
        )


def build_characters_by_id(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return character records keyed by ID."""

    characters = document.get("characters", [])
    if not isinstance(characters, list):
        return {}
    return {
        character["id"]: character
        for character in characters
        if isinstance(character, dict) and isinstance(character.get("id"), str)
    }


def summarize_character(character: dict[str, Any]) -> dict[str, Any]:
    """Build a compact character payload for provider prompts."""

    return {
        "id": character.get("id"),
        "name": character.get("name"),
        "role": character.get("role"),
        "description": character.get("description", ""),
        "motivation": character.get("motivation", ""),
        "voice": character.get("voice", ""),
    }


def summarize_adaptation(document: dict[str, Any]) -> dict[str, Any]:
    """Build a compact adaptation-strategy payload to steer scene drafting."""

    adaptation = document.get("adaptation")
    adaptation = adaptation if isinstance(adaptation, dict) else {}
    strategy = adaptation.get("strategy")
    strategy = strategy if isinstance(strategy, dict) else {}
    return {
        "target_format": adaptation.get("target_format", "screenplay"),
        "target_runtime_min": adaptation.get("target_runtime_min"),
        "fidelity": strategy.get("fidelity", "balanced"),
        "pacing": strategy.get("pacing", "compressed"),
        "dialogue_style": strategy.get("dialogue_style", "natural"),
        "narration_policy": strategy.get("narration_policy", "convert_to_action_or_dialogue"),
    }
