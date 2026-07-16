"""Daily engagement caps — shared with operator store."""

from __future__ import annotations

from dataclasses import dataclass

from ..operator.store import OperatorStore


@dataclass
class BudgetSnapshot:
    comment_likes_used: int
    comment_likes_cap: int
    reels_scrolled: int
    reels_scrolled_cap: int

    @property
    def comment_likes_remaining(self) -> int:
        return max(0, self.comment_likes_cap - self.comment_likes_used)

    @property
    def reels_remaining(self) -> int:
        return max(0, self.reels_scrolled_cap - self.reels_scrolled)


class EngagementBudget:
    """Check and record engagement against operator daily ledger."""

    def __init__(self, store: OperatorStore | None = None) -> None:
        self.store = store or OperatorStore()

    def snapshot(self) -> BudgetSnapshot:
        daily = self.store.get_daily()
        caps = self.store.get_caps()
        return BudgetSnapshot(
            comment_likes_used=daily.comment_likes,
            comment_likes_cap=caps.comment_likes,
            reels_scrolled=daily.reels_scrolled,
            reels_scrolled_cap=caps.reels_scrolled,
        )

    def can_like_comment(self) -> bool:
        snap = self.snapshot()
        return snap.comment_likes_remaining > 0

    def can_scroll_reel(self) -> bool:
        snap = self.snapshot()
        return snap.reels_remaining > 0

    def record_comment_like(self) -> None:
        self.store.apply_engagement("like_comment", {"phase": "reels_comment_likes"})

    def record_reel_seen(self) -> None:
        self.store.apply_engagement("swipe", {"phase": "reels_comment_likes"})

    def block_reason(self) -> str | None:
        snap = self.snapshot()
        if snap.comment_likes_remaining <= 0:
            return "daily_comment_like_cap"
        if snap.reels_remaining <= 0:
            return "daily_reels_cap"
        return None
