from __future__ import annotations

import io
import wave
from abc import ABC, abstractmethod
from functools import lru_cache

import httpx

from ..config import get_settings


class TTSClient(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Return WAV audio bytes (24 kHz mono PCM16 preferred)."""


class MockTTSClient(TTSClient):
    """Generates a short silent WAV so the phone playback path is testable without GPU."""

    async def synthesize(self, text: str) -> bytes:
        duration_s = min(2.0, max(0.4, len(text) * 0.04))
        sample_rate = 24_000
        n_frames = int(sample_rate * duration_s)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x00" * n_frames)
        return buf.getvalue()


class OmniVoiceHTTPClient(TTSClient):
    """Calls the self-hosted OmniVoice HTTP service (see infra/omnivoice/serve.py)."""

    def __init__(self, base_url: str, instruct: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.instruct = instruct
        self._client = httpx.AsyncClient(timeout=timeout)

    async def synthesize(self, text: str) -> bytes:
        resp = await self._client.post(
            f"{self.base_url}/synthesize",
            json={"text": text, "instruct": self.instruct},
        )
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "audio" in ct:
            return resp.content
        # JSON fallback { "audio_b64": "..." }
        data = resp.json()
        import base64

        return base64.b64decode(data["audio_b64"])


@lru_cache
def get_tts() -> TTSClient:
    s = get_settings()
    provider = s.tts_provider.lower()
    if provider == "omnivoice":
        return OmniVoiceHTTPClient(base_url=s.omnivoice_url, instruct=s.omnivoice_instruct)
    return MockTTSClient()
