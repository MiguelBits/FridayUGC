"""Inbox sync — fetch DMs/comments, brain policy, send via instagrapi."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..config import get_settings
from ..inbox.composer import evaluate_inbox
from ..inbox.schemas import IncomingMessage
from ..inbox.store import InboxStore
from .client import FridayInstagramClient, get_instagram_client

logger = logging.getLogger(__name__)


def _fetch_dm_messages(cl: Any, *, limit: int = 20) -> list[IncomingMessage]:
    out: list[IncomingMessage] = []
    threads = cl.direct_threads(amount=min(limit, 30))
    for thread in threads:
        thread_id = str(getattr(thread, "id", "") or getattr(thread, "pk", ""))
        users = getattr(thread, "users", []) or []
        peer = users[0] if users else None
        author = getattr(peer, "username", "") if peer else "unknown"
        messages = getattr(thread, "messages", []) or []
        for msg in messages[:5]:
            text = getattr(msg, "text", "") or ""
            if not text.strip():
                continue
            out.append(
                IncomingMessage(
                    message_id=str(getattr(msg, "id", "") or getattr(msg, "pk", "")),
                    thread_id=thread_id,
                    author=author,
                    text=text.strip(),
                    channel="dm",
                )
            )
    return out[:limit]


def _fetch_comment_messages(cl: Any, *, limit: int = 20) -> list[IncomingMessage]:
    out: list[IncomingMessage] = []
    user_id = cl.user_id
    medias = cl.user_medias(user_id, amount=5)
    for media in medias:
        media_id = str(getattr(media, "pk", ""))
        if not media_id:
            continue
        try:
            comments = cl.media_comments(media_id, amount=15)
        except Exception:
            continue
        for comment in comments:
            author = getattr(getattr(comment, "user", None), "username", "") or "unknown"
            text = getattr(comment, "text", "") or ""
            if not text.strip():
                continue
            out.append(
                IncomingMessage(
                    message_id=str(getattr(comment, "pk", "")),
                    thread_id=media_id,
                    author=author,
                    text=text.strip(),
                    channel="comment",
                    post_id=media_id,
                )
            )
            if len(out) >= limit:
                return out
    return out


async def _evaluate(messages: list[IncomingMessage]) -> tuple[list[Any], str]:
    return await evaluate_inbox(messages, draft_if_reply=True)


def process_inbox(
    *,
    dm_limit: int = 15,
    comment_limit: int = 15,
    send: bool = True,
    read_only: bool | None = None,
) -> dict[str, Any]:
    """Fetch inbox, run Lorena policy, optionally send approved replies."""
    settings = get_settings()
    read_only = settings.ig_read_only if read_only is None else read_only
    ig = get_instagram_client()
    cl = ig.client()

    messages = _fetch_dm_messages(cl, limit=dm_limit)
    messages.extend(_fetch_comment_messages(cl, limit=comment_limit))
    if not messages:
        return {"ok": True, "fetched": 0, "sent": 0, "skipped": 0}

    decisions, summary, global_today, global_cap = asyncio.run(_evaluate(messages))
    sent = 0
    skipped = 0
    store = InboxStore()

    for d in decisions:
        if d.action != "reply" or not d.draft:
            skipped += 1
            continue
        if d.approval_required and settings.ig_require_approval:
            logger.info("Needs approval — skip @%s: %s", d.author, d.reason)
            skipped += 1
            continue
        if read_only or not send:
            logger.info("[read-only] would reply to @%s: %s", d.author, d.draft)
            skipped += 1
            continue

        msg = next((m for m in messages if m.message_id == d.message_id), None)
        if not msg:
            skipped += 1
            continue

        ig.human_pause(2.0, 6.0)
        try:
            if msg.channel == "dm":
                thread = cl.direct_thread(msg.thread_id)
                user_ids = [u.pk for u in getattr(thread, "users", [])]
                cl.direct_send(d.draft, user_ids=user_ids, thread_ids=[int(msg.thread_id)])
            else:
                cl.media_comment(msg.post_id, d.draft, replied_to_comment_id=int(msg.message_id))
            store.record_reply(
                user=msg.author,
                channel=msg.channel,
                message_id=msg.message_id,
                thread_id=msg.thread_id,
                text_sent=d.draft,
            )
            sent += 1
        except Exception as exc:
            logger.warning("Reply failed for @%s: %s", d.author, exc)
            skipped += 1

    return {
        "ok": True,
        "fetched": len(messages),
        "sent": sent,
        "skipped": skipped,
        "policy_summary": summary,
        "global_replies_today": global_today,
        "global_cap_today": global_cap,
    }
