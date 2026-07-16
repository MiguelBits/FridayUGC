from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .schemas import DayPlanRequest, DayPlanResponse, TaskRecord
from .store import OperatorStore


def _resolve_tz(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        pass
    try:
        return ZoneInfo("America/New_York")
    except Exception:
        return timezone.utc


class DayPlanner:
    """Generate micro-sessions spread across the day."""

    def __init__(self, store: OperatorStore | None = None) -> None:
        self.store = store or OperatorStore()

    def build(self, req: DayPlanRequest) -> DayPlanResponse:
        tz = _resolve_tz(req.timezone)
        today = datetime.now(tz).date()
        day_str = today.isoformat()
        now = datetime.now(tz)
        if req.reels_only:
            slots = self._reels_only_slots(today, tz, req, now)
        else:
            slots = self._slots(today, tz, req, now)
        tasks: list[TaskRecord] = []
        for slot, kind, goal, ctx, max_steps in slots:
            tasks.append(
                TaskRecord(
                    task_id=str(uuid.uuid4()),
                    kind=kind,
                    goal=goal,
                    scheduled_at=slot.isoformat(),
                    mode=req.mode,
                    session_context=ctx,
                    max_steps=max_steps,
                )
            )
        self.store.replace_tasks_for_day(day_str, tasks)
        return DayPlanResponse(
            date=day_str,
            tasks=tasks,
            strategy_notes=(
                f"Planned {len(tasks)} micro-sessions for {day_str} "
                f"with {req.comment_likes_target} comment-like budget."
            ),
        )

    def _reels_only_slots(
        self,
        today: date,
        tz: ZoneInfo,
        req: DayPlanRequest,
        now: datetime,
    ) -> list[tuple[datetime, str, str, dict, int]]:
        start = datetime.combine(today, datetime.min.time(), tzinfo=tz).replace(hour=9)
        end = datetime.combine(today, datetime.min.time(), tzinfo=tz).replace(hour=21)
        sessions = max(1, req.reels_sessions)
        per_session = max(5, req.comment_likes_target // sessions)
        per_reels = max(3, req.reels_target // sessions)
        slots: list[tuple[datetime, str, str, dict, int]] = []

        slots.append(
            (
                now,
                "reels_comment_likes",
                f"Like comments on {per_reels} reels in Reels tab",
                {
                    "phase": "reels_comment_likes",
                    "comment_likes_target": per_session,
                    "comment_likes_done": 0,
                    "reels_scrolled": 0,
                    "reels_target": per_reels,
                },
                50,
            )
        )

        for i in range(sessions - 1):
            span = max(1, 12 // sessions)
            at = start + timedelta(hours=i * span, minutes=random.randint(0, 30))
            if at > end:
                continue
            slots.append(
                (
                    at,
                    "reels_comment_likes",
                    f"Like comments on {per_reels} reels in Reels tab",
                    {
                        "phase": "reels_comment_likes",
                        "comment_likes_target": per_session,
                        "comment_likes_done": 0,
                        "reels_scrolled": 0,
                        "reels_target": per_reels,
                    },
                    50,
                )
            )

        slots.sort(key=lambda s: s[0])
        return slots

    def _slots(
        self,
        today: date,
        tz: ZoneInfo,
        req: DayPlanRequest,
        now: datetime,
    ) -> list[tuple[datetime, str, str, dict, int]]:
        start = datetime.combine(today, datetime.min.time(), tzinfo=tz).replace(hour=8)
        end = datetime.combine(today, datetime.min.time(), tzinfo=tz).replace(hour=22)
        slots: list[tuple[datetime, str, str, dict, int]] = []

        # Immediate claimable warmup for devices syncing plan now
        slots.append(
            (
                now,
                "warmup",
                "Open Instagram and warm up with a short reels scroll",
                {"phase": "warmup"},
                12,
            )
        )

        # Warmup scroll
        slots.append(
            (
                start + timedelta(minutes=5),
                "warmup",
                "Open Instagram and warm up with a short reels scroll",
                {"phase": "warmup"},
                12,
            )
        )

        # Comment likes split into 4 sessions
        per_session = max(5, req.comment_likes_target // 4)
        for i in range(4):
            at = start + timedelta(hours=2 + i * 3, minutes=random.randint(0, 45))
            if at > end:
                continue
            slots.append(
                (
                    at,
                    "reels_comment_likes",
                    f"Like comments on {per_session} reels in Reels tab",
                    {
                        "phase": "reels_comment_likes",
                        "comment_likes_target": per_session,
                        "comment_likes_done": 0,
                        "reels_scrolled": 0,
                        "reels_target": max(3, req.reels_target // 4),
                    },
                    50,
                )
            )

        # Feed engagement
        slots.append(
            (
                start + timedelta(hours=6),
                "feed_engagement",
                "Scroll home feed and like a few posts naturally",
                {"phase": "feed", "likes_target": 8},
                25,
            )
        )

        if req.include_stories:
            for hour in (11, 16, 20):
                at = datetime.combine(today, datetime.min.time(), tzinfo=tz).replace(hour=hour)
                slots.append(
                    (
                        at,
                        "post_story",
                        "Post next due story from gallery queue",
                        {"phase": "post_story"},
                        35,
                    )
                )

        if req.include_post:
            prime = datetime.combine(today, datetime.min.time(), tzinfo=tz).replace(hour=19, minute=15)
            slots.append(
                (
                    prime,
                    "post_reel",
                    "Post next due reel with caption and location",
                    {"phase": "post_reel"},
                    45,
                )
            )

        slots.append(
            (
                end - timedelta(minutes=20),
                "inbox",
                "Check inbox and reply to pending DMs per policy",
                {"phase": "inbox"},
                20,
            )
        )

        slots.sort(key=lambda s: s[0])
        return slots
