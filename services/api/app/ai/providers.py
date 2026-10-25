"""Provider-neutral AI gateway.

The mock provider is the default and is always labelled ``mock=True``. Real providers are only
selected when ``BUSINEX_AI_PROVIDER`` names them *and* credentials are configured; otherwise the
gateway falls back to the mock. A real provider that fails after its retries raises
``ProviderError`` - it never silently substitutes mock text for a real answer.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.config import Settings

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    """The upstream AI provider could not produce an answer."""


@dataclass
class GenerationResult:
    text: str
    tokens_in: int
    tokens_out: int
    provider: str
    mock: bool
    estimated_cost: float


class Provider(ABC):
    name: str
    mock: bool = False

    @abstractmethod
    async def generate(self, prompt: str) -> GenerationResult:
        raise NotImplementedError


class MockProvider(Provider):
    name = "mock"
    mock = True

    async def generate(self, prompt: str) -> GenerationResult:
        excerpt = prompt.strip().replace("\n", " ")[:180]
        text = (
            "This is a mock AI response for offline development. "
            f"It restates your request without calling a paid provider: {excerpt}. "
            "Cite only authorized course materials and keep a human in the loop for grades."
        )
        tokens_in = max(1, len(prompt) // 4)
        tokens_out = max(1, len(text) // 4)
        return GenerationResult(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            provider=self.name,
            mock=True,
            estimated_cost=round((tokens_in + tokens_out) * 0.000002, 6),
        )


class HttpProvider(Provider):
    """Shared HTTP behaviour: timeout, bounded retry with backoff, error mapping."""

    cost_per_token = 0.000002

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
        backoff: float = 0.5,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.transport = transport
        self.backoff = backoff

    async def _post(self, url: str, headers: dict, body: dict) -> dict:
        last_error = "unknown error"
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.post(url, headers=headers, json=body)
                except httpx.HTTPError as error:
                    last_error = f"{type(error).__name__}"
                else:
                    if response.status_code == 200:
                        return response.json()
                    last_error = f"HTTP {response.status_code}"
                    if response.status_code not in RETRYABLE_STATUS:
                        break
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff * (2**attempt))
        # The upstream body is deliberately not echoed: it may contain prompt text or key hints.
        raise ProviderError(f"{self.name} request failed ({last_error})")

    def _result(self, text: str, tokens_in: int, tokens_out: int) -> GenerationResult:
        if not text:
            raise ProviderError(f"{self.name} returned an empty response")
        return GenerationResult(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            provider=self.name,
            mock=False,
            estimated_cost=round((tokens_in + tokens_out) * self.cost_per_token, 6),
        )


def _chat_text(payload: dict) -> tuple[str, int, int]:
    try:
        text = payload["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as error:
        raise ProviderError("provider response had an unexpected shape") from error
    usage = payload.get("usage") or {}
    return text.strip(), int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


class OpenAIProvider(HttpProvider):
    name = "openai"

    def __init__(
        self, api_key: str, model: str = "gpt-4o-mini", base_url: str = "https://api.openai.com/v1", **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def generate(self, prompt: str) -> GenerationResult:
        payload = await self._post(
            f"{self.base_url}/chat/completions",
            {"Authorization": f"Bearer {self.api_key}"},
            {"model": self.model, "messages": [{"role": "user", "content": prompt}]},
        )
        return self._result(*_chat_text(payload))


class AzureOpenAIProvider(HttpProvider):
    name = "azure_openai"

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str = "",
        api_version: str = "2024-10-21",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.deployment = deployment
        self.api_version = api_version

    async def generate(self, prompt: str) -> GenerationResult:
        if not self.deployment:
            raise ProviderError("azure_openai requires BUSINEX_AZURE_OPENAI_DEPLOYMENT")
        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions"
            f"?api-version={self.api_version}"
        )
        payload = await self._post(
            url, {"api-key": self.api_key}, {"messages": [{"role": "user", "content": prompt}]}
        )
        return self._result(*_chat_text(payload))


class GeminiProvider(HttpProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash", **kwargs) -> None:
        super().__init__(**kwargs)
        self.api_key = api_key
        self.model = model

    async def generate(self, prompt: str) -> GenerationResult:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = await self._post(
            url,
            {"x-goog-api-key": self.api_key},
            {"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
        )
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("provider response had an unexpected shape") from error
        usage = payload.get("usageMetadata") or {}
        return self._result(
            text.strip(),
            int(usage.get("promptTokenCount", 0)),
            int(usage.get("candidatesTokenCount", 0)),
        )


def get_provider(settings: Settings) -> Provider:
    name = settings.ai_provider.lower()
    options = {"timeout": settings.ai_timeout_seconds, "max_retries": settings.ai_max_retries}
    if name == "openai" and settings.openai_api_key:
        return OpenAIProvider(
            settings.openai_api_key, settings.openai_model, settings.openai_base_url, **options
        )
    if name == "azure_openai" and settings.azure_openai_api_key and settings.azure_openai_endpoint:
        return AzureOpenAIProvider(
            settings.azure_openai_api_key,
            settings.azure_openai_endpoint,
            settings.azure_openai_deployment,
            settings.azure_openai_api_version,
            **options,
        )
    if name == "gemini" and settings.gemini_api_key:
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model, **options)
    return MockProvider()


def tokenize_overlap(query: str, body: str) -> float:
    q = {part.lower() for part in query.split() if len(part) > 3}
    b = {part.lower() for part in body.split() if len(part) > 3}
    if not q or not b:
        return 0.0
    return len(q & b) / len(q)
