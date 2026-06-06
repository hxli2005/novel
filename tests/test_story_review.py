import json

from novel_to_screenplay.pipeline.story_review import (
    normalize_review_findings,
    review_story_with_llm,
)
from novel_to_screenplay.providers import ChatMessage, ProviderCompletion


def build_document() -> dict:
    return {
        "story_world": {"logline": "L", "synopsis": "S"},
        "characters": [{"id": "char_001", "name": "甲", "role": "protagonist"}],
        "scenes": [
            {"id": "sc_001", "summary": "开场", "characters_present": ["char_001"], "beats": []},
            {"id": "sc_002", "summary": "结尾", "characters_present": ["char_001"], "beats": []},
        ],
    }


class FindingsProvider:
    name = "fake"
    model = "fake-review"

    def __init__(self, payload: object) -> None:
        self.payload = payload

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> ProviderCompletion:
        del messages, temperature, max_tokens
        return ProviderCompletion(
            text=json.dumps(self.payload, ensure_ascii=False),
            provider=self.name,
            model=self.model,
            usage={},
        )


def test_normalize_review_findings_filters_codes_and_scene_ids() -> None:
    raw = [
        {"code": "FORESHADOW_UNRESOLVED", "message": "钥匙没回收", "scene_id": "sc_001"},
        {"code": "ARC_INCONSISTENCY", "message": "弧光跳跃", "scene_id": "sc_999"},
        {"code": "BOGUS_CODE", "message": "应被丢弃"},
        {"code": "CAUSALITY_GAP", "message": "   "},
        "not a dict",
    ]

    findings = normalize_review_findings(raw, {"sc_001", "sc_002"})

    assert [f.code for f in findings] == ["FORESHADOW_UNRESOLVED", "ARC_INCONSISTENCY"]
    assert findings[0].scene_id == "sc_001"
    assert findings[1].scene_id is None  # unknown scene id dropped, finding kept


def test_review_story_with_llm_returns_normalized_findings() -> None:
    provider = FindingsProvider(
        [{"code": "CAUSALITY_GAP", "message": "因果断裂。", "scene_id": "sc_002"}]
    )

    findings = review_story_with_llm(build_document(), provider)

    assert len(findings) == 1
    assert findings[0].code == "CAUSALITY_GAP"
    assert findings[0].scene_id == "sc_002"


def test_review_story_with_llm_empty_on_malformed_response() -> None:
    class MalformedProvider:
        name = "fake"
        model = "fake"

        def complete(self, messages, *, temperature=0.2, max_tokens=2048):  # type: ignore[no-untyped-def]
            del messages, temperature, max_tokens
            return ProviderCompletion(
                text="抱歉，我无法返回 JSON。", provider="fake", model="fake", usage={}
            )

    assert review_story_with_llm(build_document(), MalformedProvider()) == []
