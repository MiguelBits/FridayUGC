from __future__ import annotations

import time
from dataclasses import dataclass, field

# Staples that may appear at most once per COOLDOWN_WINDOW reels (from DIRECTOR_FLOW hype budget).
COOLDOWN_STAPLES: frozenset[str] = frozenset(
    {
        "ten out of ten",
        "i'm dead",
        "girlies",
        "obsessed",
        "never skip leg day",
        "good dog",
        "stop",
        "this combo is it",
    }
)

COOLDOWN_WINDOW = 5  # reels


@dataclass
class RotationTracker:
    """Tracks recent phrase usage per persona to enforce anti-repetition.

    In-memory by default. For multi-worker deployments back this with Redis using
    the same interface (record / on_cooldown).
    """

    window: int = COOLDOWN_WINDOW
    _recent: list[set[str]] = field(default_factory=list)  # newest last, len <= window
    _last_touch: float = field(default_factory=time.time)

    def on_cooldown(self, phrase: str) -> bool:
        p = phrase.strip().lower()
        if p not in COOLDOWN_STAPLES:
            return False
        return any(p in bucket for bucket in self._recent)

    def filter_available(self, phrases: list[str]) -> list[str]:
        """Return phrases that are not currently on cooldown (order preserved)."""
        return [p for p in phrases if not self.on_cooldown(p)]

    def record(self, phrases: list[str]) -> None:
        """Record the staples used in one reel and advance the window."""
        used = {p.strip().lower() for p in phrases if p.strip().lower() in COOLDOWN_STAPLES}
        self._recent.append(used)
        if len(self._recent) > self.window:
            self._recent.pop(0)
        self._last_touch = time.time()

    def recent_staples(self) -> list[str]:
        """Staples used in the current cooldown window (for curator prompts)."""
        seen: set[str] = set()
        for bucket in self._recent:
            seen.update(bucket)
        return sorted(seen)
