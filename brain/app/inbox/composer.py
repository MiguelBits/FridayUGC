from __future__ import annotations

from ..config import get_settings
from ..llm import ChatMessage, get_llm
from ..persona import get_persona
from ..ugc import safety
from .policy import evaluate_one
from .schemas import IncomingMessage, MessageDecision
from .store import InboxStore


async def draft_reply(
    msg: IncomingMessage,
    persona_key: str = "lorena",
) -> str:
    persona = get_persona(persona_key)
    llm = get_llm()
    channel_label = "DM" if msg.channel == "dm" else "comment"
    user = (
        "RETURN_INBOX_DRAFT\n"
        f"Write ONE short Instagram {channel_label} reply (<=22 words) in Lorena's voice. "
        "Sassy, not sweet. No hashtags. One concrete detail if natural. "
        "Do not over-engage — this account does not reply to everyone.\n\n"
        f"From @{msg.author}: {msg.text!r}"
    )
    raw = await llm.chat(
        [ChatMessage("system", persona.system_prompt), ChatMessage("user", user)],
        max_tokens=80,
    )
    return safety.sanitize_dialogue(raw.strip())


async def evaluate_inbox(
    messages: list[IncomingMessage],
    *,
    draft_if_reply: bool = True,
    persona_key: str = "lorena",
) -> tuple[list[MessageDecision], str, int, int]:
    store = InboxStore()
    settings = get_settings()
    decisions: list[MessageDecision] = []

    for msg in messages:
        d = evaluate_one(msg, store, settings)
        if d.action == "reply" and draft_if_reply:
            d.draft = await draft_reply(msg, persona_key)
        decisions.append(d)

    global_today = len(store.replies_on_date())
    summary = (
        f"Policy: max {settings.inbox_max_replies_per_user_per_day}/user/day "
        f"({settings.inbox_max_replies_global_per_day} global). "
        "Not every message gets a reply — low-effort pings often skipped."
    )
    return decisions, summary, global_today, settings.inbox_max_replies_global_per_day
