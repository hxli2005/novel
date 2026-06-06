"""Robust structured (JSON) output parsing and provider orchestration.

Real LLM providers routinely wrap JSON in Markdown code fences, add a sentence
of explanation before or after it, or leave a trailing comma. These helpers
extract the intended JSON value from such responses and, when a provider call
is available, retry once with a repair instruction before giving up.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from novel_to_screenplay.providers import ChatMessage, ProviderError

JsonShape = Literal["object", "array"]


class StructuredOutputError(ProviderError):
    """Raised when a provider response cannot be parsed as the expected JSON."""


def extract_json_value(text: str) -> Any:
    """Parse the first JSON object or array embedded in a provider response.

    Tolerates Markdown code fences, surrounding prose, and trailing commas.
    """

    cleaned = text.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    span = _find_first_json_span(cleaned)
    if span is None:
        raise StructuredOutputError("provider response did not contain JSON.")
    try:
        return json.loads(span)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_remove_trailing_commas(span))
    except json.JSONDecodeError as exc:
        raise StructuredOutputError("provider response was not valid JSON.") from exc


def complete_json(
    provider: Any,
    messages: list[ChatMessage],
    *,
    expect: JsonShape | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    max_retries: int = 1,
) -> Any:
    """Call a provider and parse a JSON value, retrying with a repair prompt.

    On a parse failure or a top-level type mismatch (when ``expect`` is set),
    the previous answer and a repair instruction are appended and the provider
    is called again, up to ``max_retries`` extra times.
    """

    conversation = list(messages)
    last_error = StructuredOutputError("provider did not return valid JSON.")
    for _ in range(max_retries + 1):
        completion = provider.complete(
            conversation,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            value = extract_json_value(completion.text)
            _check_shape(value, expect)
            return value
        except StructuredOutputError as exc:
            last_error = exc
            conversation = [
                *messages,
                ChatMessage(role="assistant", content=completion.text),
                ChatMessage(role="user", content=_repair_instruction(expect)),
            ]
    raise last_error


def _check_shape(value: Any, expect: JsonShape | None) -> None:
    if expect == "object" and not isinstance(value, dict):
        raise StructuredOutputError("expected a JSON object.")
    if expect == "array" and not isinstance(value, list):
        raise StructuredOutputError("expected a JSON array.")


def _repair_instruction(expect: JsonShape | None) -> str:
    shape = {"object": "JSON 对象", "array": "JSON 数组"}.get(expect or "", "JSON")
    return (
        f"你上一条输出无法解析。请只返回合法的 {shape}，"
        "不要使用 Markdown 代码块，不要添加任何解释文字。"
    )


def _find_first_json_span(text: str) -> str | None:
    """Return the first balanced ``{...}`` or ``[...]`` span, or None."""

    start = next((i for i, ch in enumerate(text) if ch in "[{"), None)
    if start is None:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _remove_trailing_commas(text: str) -> str:
    """Drop commas that directly precede a closing ``]`` or ``}``."""

    out: list[str] = []
    in_string = False
    escape = False
    for index, char in enumerate(text):
        if in_string:
            out.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            out.append(char)
            continue
        if char == ",":
            rest = text[index + 1 :].lstrip()
            if rest[:1] in {"]", "}"}:
                continue
        out.append(char)
    return "".join(out)
