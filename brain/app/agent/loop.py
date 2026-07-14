"""Agent loop entrypoints — prefer importing decide from router."""

from .router import decide, decide_legacy

__all__ = ["decide", "decide_legacy"]
