from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from ..config import Settings, get_settings
from .schemas import Channel, IncomingMessage, MessageDecision
from .store import InboxStore

_LOW_EFFORT = re.compile(
    r"^(hi+|hey+|hello+|yo+|sup+|hii+|heyy*|ok+|k+|👋|🙏|❤️|[!.?\s])+?$",
    re.IGNORECASE,
)


def _stable_roll(user: str, message_id: str, salt: str) -> float:
    """Deterministic 0..1 float — same inputs always same roll (human-ish, testable)."""
    raw = f"{user}:{message_id}:{salt}".encode()
    h = hashlib.sha256(raw).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def is_low_effort(text: str) -> bool:
    t = text.strip()
    if len(t) <= 2:
        return True
    if len(t) < 20 and _LOW_EFFORT.match(t):
        return True
    return False


def hours_since(iso_at: str) -> float:
    try:
        then = datetime.fromisoformat(iso_at.replace("Z", "+00:00"))
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - then
        return delta.total_seconds() / 3600.0
    except ValueError:
        return 999.0


def cap_for_channel(settings: Settings, channel: Channel) -> int:
    if channel == "comment":
        return settings.inbox_comment_max_per_user_per_day
    return settings.inbox_max_replies_per_user_per_day


def evaluate_one(
    msg: IncomingMessage,
    store: InboxStore,
    settings: Settings | None = None,
) -> MessageDecision:
    """Decide reply / skip / defer — not every message gets an answer."""
    s = settings or get_settings()
    user = msg.author.lower().lstrip("@")
    cap = cap_for_channel(s, msg.channel)
    user_today = store.user_replies_today(user, msg.channel)
    global_today = len(store.replies_on_date())

    base = MessageDecision(
        message_id=msg.message_id,
        author=user,
        channel=msg.channel,
        action="skip",
        reason="",
        replies_today_for_user=user_today,
        cap_per_user_per_day=cap,
        approval_required=False,
    )

    if user_today >= cap:
        base.reason = f"daily_cap_per_user ({user_today}/{cap})"
        return base

    if global_today >= s.inbox_max_replies_global_per_day:
        base.action = "defer"
        base.reason = f"global_daily_cap ({global_today}/{s.inbox_max_replies_global_per_day})"
        return base

    last = store.last_reply_to_user(user)
    if last and hours_since(last.at) < s.inbox_min_hours_between_same_user:
        base.action = "defer"
        base.reason = f"cooldown_same_user (<{s.inbox_min_hours_between_same_user}h since last)"
        return base

    if s.inbox_skip_low_effort and is_low_effort(msg.text):
        roll = _stable_roll(user, msg.message_id, "low_effort")
        if roll > s.inbox_low_effort_reply_probability:
            base.reason = "low_effort_skip (hi/hey — not replying to every ping)"
            return base

    # Borderline: don't reply to every message even under cap — paced by handle hash.
    roll = _stable_roll(user, msg.message_id, "pace")
    if roll > s.inbox_reply_pace_probability:
        base.action = "defer"
        base.reason = "paced_defer (human rhythm — will revisit next inbox poll)"
        return base

    base.action = "reply"
    base.reason = "within_caps_and_policy"
    base.approval_required = msg.channel in s.approval_action_set
    return base
