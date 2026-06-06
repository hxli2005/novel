import json
from pathlib import Path

import pytest

from novel_to_screenplay.pipeline.chapter_parser import parse_chapters_file
from novel_to_screenplay.pipeline.entity_analyzer import analyze_chapters
from novel_to_screenplay.pipeline.scene_drafter import (
    SceneDraftError,
    build_scene_prompt,
    draft_screenplay_scenes,
    summarize_adaptation,
)
from novel_to_screenplay.pipeline.scene_outliner import build_scene_outline
from novel_to_screenplay.pipeline.screenplay_generator import (
    ScreenplayGenerationOptions,
    build_screenplay_document,
)
from novel_to_screenplay.providers import ChatMessage, MockProvider, ProviderCompletion


class JsonDraftProvider:
    name = "fake"
    model = "fake-scene-model"

    def __init__(self, character_id: str, character_name: str) -> None:
        self.character_id = character_id
        self.character_name = character_name
        self.messages: list[ChatMessage] = []

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> ProviderCompletion:
        self.messages = messages
        return ProviderCompletion(
            text=json.dumps(
                [
                    {
                        "type": "action",
                        "text": "灯光压低，人物在沉默中交换眼神。",
                    },
                    {
                        "type": "dialogue",
                        "character_id": self.character_id,
                        "character_name": self.character_name,
                        "text": "我已经知道答案了。",
                    },
                ],
                ensure_ascii=False,
            ),
            provider=self.name,
            model=self.model,
            usage={},
        )


class InvalidJsonProvider:
    name = "fake"
    model = "fake-scene-model"

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> ProviderCompletion:
        del messages, temperature, max_tokens
        return ProviderCompletion(
            text="not json",
            provider=self.name,
            model=self.model,
            usage={},
        )


def test_draft_screenplay_scenes_uses_provider_json_response() -> None:
    document = build_fixture_document()
    first_character_id = document["scenes"][0]["characters_present"][0]
    first_character_name = next(
        character["name"]
        for character in document["characters"]
        if character["id"] == first_character_id
    )
    provider = JsonDraftProvider(first_character_id, first_character_name)

    result = draft_screenplay_scenes(document, provider, scene_limit=1)

    first_scene = result.document["scenes"][0]
    assert result.drafted_scene_ids == ["sc_001"]
    assert result.provider == "fake"
    assert first_scene["revision_status"] == "ai_drafted"
    assert first_scene["script"][0]["type"] == "action"
    assert first_scene["script"][1]["character_id"] == first_character_id
    assert first_scene["script"][0]["source_refs"][0]["chapter_id"] == "ch_001"
    assert "output_contract" in provider.messages[1].content
    assert result.document["scenes"][1]["revision_status"] == "ai_draft"


def test_draft_screenplay_scenes_supports_mock_provider() -> None:
    document = build_fixture_document()

    result = draft_screenplay_scenes(document, MockProvider())

    assert result.provider == "mock"
    assert [scene["revision_status"] for scene in result.document["scenes"]] == [
        "ai_drafted",
        "ai_drafted",
        "ai_drafted",
    ]
    assert result.document["scenes"][0]["script"][0]["type"] == "action"
    assert any(
        warning["code"] == "AI_SCENE_DRAFTING"
        for warning in result.document["quality_report"]["warnings"]
    )


def test_draft_screenplay_scenes_rejects_invalid_provider_output() -> None:
    document = build_fixture_document()

    with pytest.raises(SceneDraftError):
        draft_screenplay_scenes(document, InvalidJsonProvider(), scene_limit=1)


def test_build_scene_prompt_includes_adaptation_strategy() -> None:
    document = {
        "adaptation": {
            "target_format": "microdrama_episode",
            "target_runtime_min": 2,
            "strategy": {"fidelity": "faithful", "pacing": "fast"},
        },
        "story_world": {},
        "characters": [{"id": "char_001", "name": "甲"}],
    }
    scene = {"id": "sc_001", "characters_present": ["char_001"], "chapter_refs": ["ch_001"]}
    characters_by_id = {"char_001": {"id": "char_001", "name": "甲"}}

    messages = build_scene_prompt(document, scene, characters_by_id)

    user_content = messages[1].content
    assert "microdrama_episode" in user_content
    assert "fast" in user_content
    assert "faithful" in user_content
    # The system instruction tells the model to follow the adaptation strategy.
    assert "adaptation" in messages[0].content


def test_summarize_adaptation_falls_back_to_defaults() -> None:
    assert summarize_adaptation({}) == {
        "target_format": "screenplay",
        "target_runtime_min": None,
        "fidelity": "balanced",
        "pacing": "compressed",
        "dialogue_style": "natural",
        "narration_policy": "convert_to_action_or_dialogue",
    }


def build_fixture_document() -> dict:
    fixture = Path(__file__).resolve().parents[1] / "examples" / "novels" / "three_chapters.txt"
    chapters = parse_chapters_file(fixture)
    analysis = analyze_chapters(chapters)
    outline = build_scene_outline(analysis)
    return build_screenplay_document(
        chapters,
        analysis,
        outline,
        ScreenplayGenerationOptions(
            title="第七页",
            author="示例作者",
            created_at="2026-06-06T10:00:00+08:00",
        ),
    )
