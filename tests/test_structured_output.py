import pytest

from novel_to_screenplay.providers import ChatMessage, ProviderCompletion
from novel_to_screenplay.structured_output import (
    StructuredOutputError,
    complete_json,
    extract_json_value,
)


def test_extract_plain_json_array() -> None:
    assert extract_json_value('[{"type": "action"}]') == [{"type": "action"}]


def test_extract_json_from_code_fence() -> None:
    text = '```json\n[{"type": "note", "text": "hi"}]\n```'
    assert extract_json_value(text) == [{"type": "note", "text": "hi"}]


def test_extract_json_with_surrounding_prose() -> None:
    text = '好的，这是结果：\n{"a": 1, "b": [2, 3]}\n希望对你有帮助。'
    assert extract_json_value(text) == {"a": 1, "b": [2, 3]}


def test_extract_json_tolerates_trailing_commas() -> None:
    text = '[{"a": 1,}, {"b": 2,},]'
    assert extract_json_value(text) == [{"a": 1}, {"b": 2}]


def test_extract_json_keeps_commas_inside_strings() -> None:
    assert extract_json_value('{"text": "a, b, c"}') == {"text": "a, b, c"}


def test_extract_json_raises_without_json() -> None:
    with pytest.raises(StructuredOutputError):
        extract_json_value("there is no json here")


class ScriptedProvider:
    """Provider that returns a fixed sequence of texts across calls."""

    name = "scripted"
    model = "scripted-model"

    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.calls: list[list[ChatMessage]] = []

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> ProviderCompletion:
        self.calls.append(list(messages))
        text = self.texts[min(len(self.calls) - 1, len(self.texts) - 1)]
        return ProviderCompletion(text=text, provider=self.name, model=self.model, usage={})


def test_complete_json_returns_first_valid_response() -> None:
    provider = ScriptedProvider(['{"ok": true}'])
    messages = [ChatMessage(role="user", content="go")]

    value = complete_json(provider, messages, expect="object")

    assert value == {"ok": True}
    assert len(provider.calls) == 1


def test_complete_json_retries_with_repair_prompt() -> None:
    provider = ScriptedProvider(["not json", '[{"type": "action"}]'])
    messages = [ChatMessage(role="user", content="go")]

    value = complete_json(provider, messages, expect="array", max_retries=1)

    assert value == [{"type": "action"}]
    assert len(provider.calls) == 2
    repair_turn = provider.calls[1]
    assert repair_turn[-1].role == "user"
    assert "JSON 数组" in repair_turn[-1].content


def test_complete_json_raises_after_exhausting_retries() -> None:
    provider = ScriptedProvider(["nope", "still nope"])
    messages = [ChatMessage(role="user", content="go")]

    with pytest.raises(StructuredOutputError):
        complete_json(provider, messages, expect="array", max_retries=1)
    assert len(provider.calls) == 2


def test_complete_json_retries_on_shape_mismatch() -> None:
    provider = ScriptedProvider(['{"not": "an array"}', "[1, 2, 3]"])
    messages = [ChatMessage(role="user", content="go")]

    value = complete_json(provider, messages, expect="array", max_retries=1)

    assert value == [1, 2, 3]
    assert len(provider.calls) == 2
