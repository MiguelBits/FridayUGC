from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str
    # JPEG base64 strings (no data: prefix) — sent as multimodal image parts when non-empty.
    images: list[str] = field(default_factory=list)


class LLMClient(ABC):
    """Provider-agnostic chat interface (text + optional vision images)."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        raise NotImplementedError

    async def aclose(self) -> None:  # pragma: no cover
        return None
