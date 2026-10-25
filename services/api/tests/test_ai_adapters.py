"""Real provider adapters, exercised against an in-process mock transport (no network, no keys)."""

import asyncio
import json

import httpx
import pytest

from app.ai.providers import (
    AzureOpenAIProvider,
    GeminiProvider,
    OpenAIProvider,
    ProviderError,
    get_provider,
)
from app.config import Settings


def run(coro):
    return asyncio.run(coro)


def transport(*responses: httpx.Response) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return httpx.MockTransport(handler), seen


OPENAI_OK = httpx.Response(
    200,
    json={
        "choices": [{"message": {"content": "  Real answer.  "}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7},
    },
)


def test_openai_parses_text_usage_and_is_not_mock() -> None:
    mock, seen = transport(OPENAI_OK)
    provider = OpenAIProvider("sk-test", transport=mock, backoff=0)
    result = run(provider.generate("hello"))
    assert result.text == "Real answer."
    assert (result.tokens_in, result.tokens_out) == (12, 7)
    assert result.mock is False and result.provider == "openai"
    assert seen[0].headers["authorization"] == "Bearer sk-test"
    assert json.loads(seen[0].content)["messages"][0]["content"] == "hello"


def test_retries_transient_errors_then_succeeds() -> None:
    mock, seen = transport(httpx.Response(503), httpx.Response(429), OPENAI_OK)
    result = run(OpenAIProvider("k", transport=mock, backoff=0, max_retries=2).generate("hi"))
    assert result.text == "Real answer."
    assert len(seen) == 3


def test_gives_up_after_retries_without_leaking_upstream_body() -> None:
    mock, seen = transport(httpx.Response(500, text="secret-prompt-echo sk-leak"))
    provider = OpenAIProvider("k", transport=mock, backoff=0, max_retries=1)
    with pytest.raises(ProviderError) as error:
        run(provider.generate("hi"))
    assert len(seen) == 2
    assert "secret-prompt-echo" not in str(error.value)
    assert "HTTP 500" in str(error.value)


def test_client_errors_are_not_retried() -> None:
    mock, seen = transport(httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(ProviderError):
        run(OpenAIProvider("bad", transport=mock, backoff=0, max_retries=3).generate("hi"))
    assert len(seen) == 1


def test_network_failure_maps_to_provider_error() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    provider = OpenAIProvider("k", transport=httpx.MockTransport(boom), backoff=0, max_retries=1)
    with pytest.raises(ProviderError):
        run(provider.generate("hi"))


def test_malformed_response_is_rejected() -> None:
    mock, _ = transport(httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(ProviderError):
        run(OpenAIProvider("k", transport=mock).generate("hi"))


def test_empty_answer_is_rejected() -> None:
    mock, _ = transport(httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}))
    with pytest.raises(ProviderError):
        run(OpenAIProvider("k", transport=mock).generate("hi"))


def test_azure_uses_deployment_url_and_api_key_header() -> None:
    mock, seen = transport(OPENAI_OK)
    provider = AzureOpenAIProvider("az-key", "https://res.openai.azure.com/", "gpt-edu", "2024-10-21", transport=mock)
    result = run(provider.generate("hi"))
    assert result.provider == "azure_openai" and result.mock is False
    assert str(seen[0].url).startswith("https://res.openai.azure.com/openai/deployments/gpt-edu/chat/completions")
    assert seen[0].headers["api-key"] == "az-key"


def test_azure_without_deployment_is_an_explicit_error() -> None:
    with pytest.raises(ProviderError):
        run(AzureOpenAIProvider("k", "https://x", "").generate("hi"))


def test_gemini_parses_candidates_and_usage() -> None:
    mock, seen = transport(
        httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "Hello "}, {"text": "world"}]}}],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
            },
        )
    )
    result = run(GeminiProvider("g-key", transport=mock).generate("hi"))
    assert result.text == "Hello world"
    assert (result.tokens_in, result.tokens_out) == (5, 3)
    assert seen[0].headers["x-goog-api-key"] == "g-key"


def test_factory_builds_real_provider_only_with_credentials() -> None:
    assert get_provider(Settings(ai_provider="openai", openai_api_key="k")).name == "openai"
    assert get_provider(Settings(ai_provider="openai")).name == "mock"
    configured = Settings(ai_provider="azure_openai", azure_openai_api_key="k", azure_openai_endpoint="https://x")
    assert get_provider(configured).name == "azure_openai"
    assert get_provider(Settings(ai_provider="gemini", gemini_api_key="k")).name == "gemini"
