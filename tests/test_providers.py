import http.client
import io
import json
import urllib.error
import urllib.request

import pytest

from novel_to_screenplay.providers import (
    ChatMessage,
    DeepSeekProvider,
    MissingProviderConfigError,
    MockProvider,
    ProviderRequestError,
    build_provider,
    get_provider_statuses,
)


def test_mock_provider_returns_deterministic_completion() -> None:
    provider = MockProvider()

    completion = provider.complete([ChatMessage(role="user", content="生成一个场景")])

    assert completion.provider == "mock"
    assert completion.model == "mock"
    assert completion.text == "mock response: 生成一个场景"


def test_build_provider_rejects_missing_deepseek_api_key() -> None:
    with pytest.raises(MissingProviderConfigError):
        build_provider("deepseek", env={})


def test_deepseek_provider_sends_openai_compatible_chat_request() -> None:
    captured: dict[str, object] = {}

    def fake_transport(request: urllib.request.Request, timeout_sec: float) -> bytes:
        captured["url"] = request.full_url
        captured["timeout_sec"] = timeout_sec
        captured["authorization"] = request.get_header("Authorization")
        captured["content_type"] = request.get_header("Content-type")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return json.dumps(
            {
                "model": "deepseek-v4-pro",
                "choices": [
                    {
                        "message": {
                            "content": "可以，我会按剧本格式生成。",
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 8,
                    "total_tokens": 20,
                },
            }
        ).encode("utf-8")

    provider = DeepSeekProvider(api_key="sk-test", transport=fake_transport, timeout_sec=5)
    completion = provider.complete(
        [
            ChatMessage(role="system", content="你是剧本助手。"),
            ChatMessage(role="user", content="确认连通。"),
        ],
        temperature=0.3,
        max_tokens=128,
    )

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["timeout_sec"] == 5
    assert captured["authorization"] == "Bearer sk-test"
    assert captured["content_type"] == "application/json"
    assert captured["body"] == {
        "model": "deepseek-v4-pro",
        "messages": [
            {
                "role": "system",
                "content": "你是剧本助手。",
            },
            {
                "role": "user",
                "content": "确认连通。",
            },
        ],
        "thinking": {
            "type": "disabled",
        },
        "temperature": 0.3,
        "max_tokens": 128,
    }
    assert completion.text == "可以，我会按剧本格式生成。"
    assert completion.provider == "deepseek"
    assert completion.model == "deepseek-v4-pro"
    assert completion.usage["total_tokens"] == 20


def test_deepseek_provider_rejects_empty_content_response() -> None:
    def fake_transport(request: urllib.request.Request, timeout_sec: float) -> bytes:
        del request, timeout_sec
        return b'{"model":"deepseek-v4-pro","choices":[{"message":{"content":""}}]}'

    provider = DeepSeekProvider(api_key="sk-test", transport=fake_transport)

    with pytest.raises(ProviderRequestError):
        provider.complete([ChatMessage(role="user", content="确认连通。")])


def test_get_provider_statuses_reports_deepseek_configuration() -> None:
    statuses = get_provider_statuses(
        {
            "DEEPSEEK_API_KEY": "sk-test",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "DEEPSEEK_THINKING": "enabled",
        }
    )

    assert statuses[0].name == "mock"
    assert statuses[0].configured
    assert statuses[1].name == "deepseek"
    assert statuses[1].configured
    assert "deepseek-v4-flash" in statuses[1].detail
    assert "thinking=enabled" in statuses[1].detail


def test_deepseek_provider_rejects_invalid_thinking_mode() -> None:
    with pytest.raises(MissingProviderConfigError):
        DeepSeekProvider(api_key="sk-test", thinking="maybe")


_OK_BODY = json.dumps({"choices": [{"message": {"content": "成稿。"}}]}).encode("utf-8")


def test_deepseek_retries_transient_connection_drop_then_succeeds() -> None:
    calls = {"n": 0}

    def flaky_transport(request: urllib.request.Request, timeout_sec: float) -> bytes:
        del request, timeout_sec
        calls["n"] += 1
        if calls["n"] < 3:
            # The exact error seen against the real API mid-run.
            raise http.client.RemoteDisconnected("Remote end closed connection without response")
        return _OK_BODY

    provider = DeepSeekProvider(
        api_key="sk-test", transport=flaky_transport, max_retries=2, retry_backoff_sec=0
    )
    completion = provider.complete([ChatMessage(role="user", content="写。")])

    assert completion.text == "成稿。"
    assert calls["n"] == 3  # two retries, then success


def test_deepseek_wraps_persistent_drop_as_provider_error() -> None:
    def dead_transport(request: urllib.request.Request, timeout_sec: float) -> bytes:
        del request, timeout_sec
        raise http.client.RemoteDisconnected("boom")

    provider = DeepSeekProvider(
        api_key="sk-test", transport=dead_transport, max_retries=1, retry_backoff_sec=0
    )
    # A raw http.client error must surface as a ProviderError, so callers can
    # fall back instead of crashing the whole run.
    with pytest.raises(ProviderRequestError):
        provider.complete([ChatMessage(role="user", content="写。")])


def test_deepseek_retries_5xx_but_not_4xx() -> None:
    auth_calls = {"n": 0}

    def auth_fail(request: urllib.request.Request, timeout_sec: float) -> bytes:
        del request, timeout_sec
        auth_calls["n"] += 1
        raise urllib.error.HTTPError("https://x", 401, "Unauthorized", {}, io.BytesIO(b"bad key"))

    provider = DeepSeekProvider(
        api_key="sk-test", transport=auth_fail, max_retries=3, retry_backoff_sec=0
    )
    with pytest.raises(ProviderRequestError):
        provider.complete([ChatMessage(role="user", content="写。")])
    assert auth_calls["n"] == 1  # 4xx fails fast, no retry

    busy_calls = {"n": 0}

    def busy_then_ok(request: urllib.request.Request, timeout_sec: float) -> bytes:
        del request, timeout_sec
        busy_calls["n"] += 1
        if busy_calls["n"] == 1:
            raise urllib.error.HTTPError("https://x", 503, "Busy", {}, io.BytesIO(b"busy"))
        return _OK_BODY

    recovered = DeepSeekProvider(
        api_key="sk-test", transport=busy_then_ok, max_retries=2, retry_backoff_sec=0
    )
    assert recovered.complete([ChatMessage(role="user", content="写。")]).text == "成稿。"
    assert busy_calls["n"] == 2  # 503 retried, then success
