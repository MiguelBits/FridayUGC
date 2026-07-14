from __future__ import annotations

import logging
from typing import Any

from ..config import get_settings

logger = logging.getLogger("friday.circuit")


class CircuitBreaker:
    """Stop autonomous runs after repeated failures."""

    def __init__(self) -> None:
        self._failures: dict[str, int] = {}
        self._tripped: dict[str, str] = {}

    def record_failure(self, session_id: str, reason: str) -> bool:
        settings = get_settings()
        count = self._failures.get(session_id, 0) + 1
        self._failures[session_id] = count
        logger.warning("session_failure session=%s count=%s reason=%s", session_id, count, reason)
        if count >= settings.operator_circuit_breaker_failures:
            self._tripped[session_id] = reason
            return True
        return False

    def record_success(self, session_id: str) -> None:
        self._failures.pop(session_id, None)
        self._tripped.pop(session_id, None)

    def is_tripped(self, session_id: str) -> str | None:
        return self._tripped.get(session_id)

    def status(self) -> dict[str, Any]:
        return {
            "active_failures": dict(self._failures),
            "tripped": dict(self._tripped),
        }


_breaker = CircuitBreaker()


def get_circuit_breaker() -> CircuitBreaker:
    return _breaker
