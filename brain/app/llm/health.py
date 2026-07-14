from __future__ import annotations

import asyncio
import logging

import httpx

from .base import ChatMessage, LLMClient

logger = logging.getLogger(__name__)


async def check_model_ready() -> dict:
    """Probe whether the configured LLM endpoint is reachable."""
    from ..config import get_settings

    s = get_settings()
    if s.agent_engine.lower() == "maf":
        if s.maf_backend.lower() == "ollama":
            provider = "ollama"
            base = f"{s.ollama_base_url.rstrip('/')}/v1"
            model = s.maf_model or s.ollama_model
            api_key = "ollama"
        else:
            return {
                "ready": bool(s.maf_azure_endpoint and (s.maf_azure_api_key or s.maf_model)),
                "provider": "azure",
                "model": s.maf_model,
                "detail": "azure configured" if s.maf_azure_endpoint else "set FRIDAY_MAF_AZURE_*",
            }
    else:
        provider = s.llm_provider.lower()

        if provider == "mock":
            return {"ready": True, "provider": provider, "detail": "mock provider"}

        if provider == "gemma_vllm":
            base = s.gemma_base_url.rstrip("/")
            model = s.gemma_model
            api_key = s.gemma_api_key
        elif provider == "ollama":
            base = f"{s.ollama_base_url.rstrip('/')}/v1"
            model = s.ollama_model
            api_key = "ollama"
        else:
            return {"ready": False, "provider": provider, "detail": f"unknown provider {provider!r}"}

    url = f"{base}/models"
    timeout = min(s.llm_timeout, 10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
            resp.raise_for_status()
        return {"ready": True, "provider": provider, "model": model, "detail": "models endpoint ok"}
    except Exception as exc:
        return {"ready": False, "provider": provider, "model": model, "detail": str(exc)}
