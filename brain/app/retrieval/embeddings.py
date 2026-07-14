from __future__ import annotations

import asyncio
import logging
import math
import re
from abc import ABC, abstractmethod
from functools import lru_cache

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingClient(ABC):
    """Provider-agnostic text embedding interface."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0]

    async def aclose(self) -> None:  # pragma: no cover
        return None


class MockEmbeddingClient(EmbeddingClient):
    """Deterministic hash-bucket embeddings for CI and offline dev."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_mock_vector(text, self.dimensions) for text in texts]


class OpenAICompatibleEmbeddingClient(EmbeddingClient):
    """OpenAI-compatible /embeddings — Ollama, vLLM, or OpenAI."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        settings = get_settings()
        attempts = max(1, settings.llm_max_retries + 1)
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                resp = await self._client.post(
                    f"{self.base_url}/embeddings",
                    json={"model": self.model, "input": texts},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                items = sorted(data["data"], key=lambda row: row["index"])
                return [row["embedding"] for row in items]
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                backoff = settings.llm_retry_backoff_s * (attempt + 1)
                logger.warning(
                    "Embedding request failed (attempt %s/%s): %s — retrying in %.1fs",
                    attempt + 1,
                    attempts,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)

        assert last_error is not None
        raise last_error

    async def aclose(self) -> None:
        await self._client.aclose()


class AzureOpenAIEmbeddingClient(EmbeddingClient):
    """Azure OpenAI embeddings deployment."""

    def __init__(
        self,
        endpoint: str,
        deployment: str,
        api_key: str,
        api_version: str = "2024-10-21",
        timeout: float = 60.0,
    ) -> None:
        endpoint = endpoint.rstrip("/")
        self.url = (
            f"{endpoint}/openai/deployments/{deployment}/embeddings"
            f"?api-version={api_version}"
        )
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        settings = get_settings()
        attempts = max(1, settings.llm_max_retries + 1)
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                resp = await self._client.post(
                    self.url,
                    json={"input": texts},
                    headers={"api-key": self.api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                items = sorted(data["data"], key=lambda row: row["index"])
                return [row["embedding"] for row in items]
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                backoff = settings.llm_retry_backoff_s * (attempt + 1)
                logger.warning(
                    "Azure embedding request failed (attempt %s/%s): %s — retrying in %.1fs",
                    attempt + 1,
                    attempts,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)

        assert last_error is not None
        raise last_error

    async def aclose(self) -> None:
        await self._client.aclose()


def _mock_vector(text: str, dimensions: int) -> list[float]:
    vec = [0.0] * dimensions
    tokens = re.findall(r"\w+", text.lower())
    if not tokens:
        return vec
    for token in tokens:
        vec[hash(token) % dimensions] += 1.0
    norm = math.sqrt(sum(value * value for value in vec)) or 1.0
    return [value / norm for value in vec]


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    """Build the embedding client selected by FRIDAY_EMBEDDING_PROVIDER."""
    settings = get_settings()
    provider = settings.embedding_provider.lower()

    if provider == "mock":
        return MockEmbeddingClient(dimensions=settings.embedding_dimensions)

    if provider == "azure":
        if not settings.embedding_azure_endpoint or not settings.embedding_azure_api_key:
            raise ValueError(
                "FRIDAY_EMBEDDING_PROVIDER=azure requires "
                "FRIDAY_EMBEDDING_AZURE_ENDPOINT and FRIDAY_EMBEDDING_AZURE_API_KEY"
            )
        deployment = settings.embedding_azure_deployment or settings.embedding_model
        return AzureOpenAIEmbeddingClient(
            endpoint=settings.embedding_azure_endpoint,
            deployment=deployment,
            api_key=settings.embedding_azure_api_key,
            api_version=settings.embedding_azure_api_version,
            timeout=settings.embedding_timeout,
        )

    if provider in {"openai", "ollama", "gemma_vllm"}:
        if provider == "ollama":
            base_url = f"{settings.ollama_base_url.rstrip('/')}/v1"
            api_key = "ollama"
            model = settings.embedding_model or "nomic-embed-text"
        elif provider == "gemma_vllm":
            base_url = settings.gemma_base_url
            api_key = settings.gemma_api_key
            model = settings.embedding_model or settings.gemma_model
        else:
            base_url = settings.embedding_base_url or settings.gemma_base_url
            api_key = settings.embedding_api_key or settings.gemma_api_key
            model = settings.embedding_model or "text-embedding-3-small"
        return OpenAICompatibleEmbeddingClient(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout=settings.embedding_timeout,
        )

    raise ValueError(f"Unknown FRIDAY_EMBEDDING_PROVIDER: {settings.embedding_provider!r}")
