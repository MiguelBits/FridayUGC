from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import LLMClient
from .mock import MockClient
from .openai_compatible import OpenAICompatibleClient


@lru_cache
def get_llm() -> LLMClient:
    """Build the LLM client selected by FRIDAY_LLM_PROVIDER.

    gemma_vllm -> self-hosted Gemma 4 on AWS GPU (vLLM OpenAI-compatible API)
    ollama     -> Ollama's OpenAI-compatible /v1 route
    mock       -> deterministic, GPU-free (default)
    """
    s = get_settings()
    provider = s.llm_provider.lower()

    if provider == "gemma_vllm":
        return OpenAICompatibleClient(
            base_url=s.gemma_base_url,
            model=s.gemma_model,
            api_key=s.gemma_api_key,
            timeout=s.llm_timeout,
        )
    if provider == "ollama":
        return OpenAICompatibleClient(
            base_url=f"{s.ollama_base_url.rstrip('/')}/v1",
            model=s.ollama_model,
            api_key="ollama",
            timeout=s.llm_timeout,
        )
    if provider == "mock":
        return MockClient()

    raise ValueError(f"Unknown FRIDAY_LLM_PROVIDER: {s.llm_provider!r}")


@lru_cache
def get_vision_llm() -> LLMClient:
    """Multimodal client for gallery frame analysis (defaults to Gemma 3 vision on vLLM)."""
    s = get_settings()
    if s.llm_provider.lower() == "mock":
        return MockClient()

    base = s.vision_base_url.strip() or s.gemma_base_url
    key = s.vision_api_key.strip() or s.gemma_api_key
    if s.llm_provider.lower() == "ollama":
        base = f"{s.ollama_base_url.rstrip('/')}/v1"
        key = "ollama"
        model = s.ollama_model
        vm = (s.vision_model or "").strip()
        # Ollama tag form e.g. gemma3:12b — not OpenAI-style google/gemma-3-12b-it
        if vm and ":" in vm and "/" not in vm:
            model = vm
    else:
        model = s.vision_model

    return OpenAICompatibleClient(base_url=base, model=model, api_key=key, timeout=180.0)
