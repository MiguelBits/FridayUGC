from __future__ import annotations

import asyncio
import logging

import httpx

from .base import ChatMessage, LLMClient

logger = logging.getLogger(__name__)


def _serialize_message(m: ChatMessage) -> dict:
    if not m.images:
        return {"role": m.role, "content": m.content}
    parts: list[dict] = [{"type": "text", "text": m.content}]
    for b64 in m.images:
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )
    return {"role": m.role, "content": parts}


class OpenAICompatibleClient(LLMClient):
    """OpenAI-compatible /chat/completions — text and multimodal (vision) messages."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout)

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        payload: dict = {
            "model": self.model,
            "messages": [_serialize_message(m) for m in messages],
            "temperature": 0.7 if temperature is None else temperature,
            "max_tokens": 512 if max_tokens is None else max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        from ..config import get_settings

        settings = get_settings()
        attempts = max(1, settings.llm_max_retries + 1)
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                resp = await self._client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                backoff = settings.llm_retry_backoff_s * (attempt + 1)
                logger.warning(
                    "LLM request failed (attempt %s/%s): %s — retrying in %.1fs",
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
