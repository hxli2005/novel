"""LLM provider abstractions and implementations."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

SUPPORTED_PROVIDER_NAMES = ("mock", "deepseek")

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"

Transport = Callable[[urllib.request.Request, float], bytes]


@dataclass(frozen=True)
class ChatMessage:
    """One chat-completion message."""

    role: str
    content: str


@dataclass(frozen=True)
class ProviderCompletion:
    """Normalized provider response."""

    text: str
    provider: str
    model: str
    usage: dict[str, Any]


@dataclass(frozen=True)
class ProviderStatus:
    """Human-readable provider configuration status."""

    name: str
    configured: bool
    detail: str


class ProviderError(RuntimeError):
    """Base provider error."""


class UnsupportedProviderError(ProviderError):
    """Raised when a provider name is unsupported."""


class MissingProviderConfigError(ProviderError):
    """Raised when provider configuration is incomplete."""


class ProviderRequestError(ProviderError):
    """Raised when a provider request fails."""


class MockProvider:
    """Deterministic provider used by tests and local demos."""

    name = "mock"
    model = "mock"

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> ProviderCompletion:
        """Return a deterministic completion without external API calls."""

        del temperature, max_tokens
        latest_user_message = next(
            (message.content for message in reversed(messages) if message.role == "user"),
            "",
        )
        text = f"mock response: {latest_user_message[:80]}"
        return ProviderCompletion(
            text=text,
            provider=self.name,
            model=self.model,
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )


class DeepSeekProvider:
    """DeepSeek OpenAI-compatible chat-completions provider."""

    name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
        timeout_sec: float = 60,
        transport: Transport | None = None,
    ) -> None:
        if not api_key:
            raise MissingProviderConfigError(
                "DEEPSEEK_API_KEY is required for provider 'deepseek'."
            )
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.transport = transport or default_transport

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DeepSeekProvider:
        """Build a DeepSeek provider from environment variables."""

        env = env or os.environ
        return cls(
            api_key=env.get("DEEPSEEK_API_KEY", ""),
            model=env.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
            base_url=env.get("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
        )

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> ProviderCompletion:
        """Call DeepSeek's OpenAI-compatible chat completion API."""

        payload = {
            "model": self.model,
            "messages": [message_to_payload(message) for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            response_body = self.transport(request, self.timeout_sec)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ProviderRequestError(f"DeepSeek API returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise ProviderRequestError(f"DeepSeek API request failed: {exc.reason}") from exc

        response = parse_json_response(response_body)
        try:
            text = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderRequestError(
                "DeepSeek API response did not contain message content."
            ) from exc

        if not isinstance(text, str) or not text:
            raise ProviderRequestError("DeepSeek API response content was empty.")

        usage = response.get("usage", {})
        return ProviderCompletion(
            text=text,
            provider=self.name,
            model=str(response.get("model", self.model)),
            usage=usage if isinstance(usage, dict) else {},
        )


def build_provider(
    provider_name: str,
    env: Mapping[str, str] | None = None,
) -> MockProvider | DeepSeekProvider:
    """Build a provider by name."""

    normalized = provider_name.strip().lower()
    if normalized == "mock":
        return MockProvider()
    if normalized == "deepseek":
        return DeepSeekProvider.from_env(env)
    supported = ", ".join(SUPPORTED_PROVIDER_NAMES)
    raise UnsupportedProviderError(
        f"Unsupported provider '{provider_name}'. Use one of: {supported}."
    )


def get_provider_statuses(env: Mapping[str, str] | None = None) -> list[ProviderStatus]:
    """Return provider configuration statuses for CLI display."""

    env = env or os.environ
    return [
        ProviderStatus(
            name="mock",
            configured=True,
            detail="local deterministic provider",
        ),
        ProviderStatus(
            name="deepseek",
            configured=bool(env.get("DEEPSEEK_API_KEY")),
            detail=(
                f"model={env.get('DEEPSEEK_MODEL', DEFAULT_DEEPSEEK_MODEL)}, "
                f"base_url={env.get('DEEPSEEK_BASE_URL', DEFAULT_DEEPSEEK_BASE_URL)}"
            ),
        ),
    ]


def message_to_payload(message: ChatMessage) -> dict[str, str]:
    """Convert a chat message into provider payload shape."""

    if message.role not in {"system", "user", "assistant"}:
        raise ProviderRequestError(f"Unsupported chat role: {message.role}")
    return {
        "role": message.role,
        "content": message.content,
    }


def parse_json_response(response_body: bytes) -> dict[str, Any]:
    """Parse a JSON provider response."""

    try:
        response = json.loads(response_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ProviderRequestError("Provider response was not valid JSON.") from exc
    if not isinstance(response, dict):
        raise ProviderRequestError("Provider response JSON must be an object.")
    return response


def default_transport(request: urllib.request.Request, timeout_sec: float) -> bytes:
    """Execute an HTTP request and return the response body."""

    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        return response.read()
