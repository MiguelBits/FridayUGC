from __future__ import annotations

import json
from datetime import date, timedelta

from ..llm import ChatMessage, get_llm
from ..persona import get_persona
from ..persona.phrase_rotation import RotationTracker
from ..retrieval.gallery import retrieve_assets_for_curation
from ..ugc import safety
from .schemas import (
    CarouselGroup,
    CommentReplyDraft,
    CommentToReply,
    CurateRequest,
    CurateResponse,
    GalleryAsset,
    ReplyRequest,
    ReplyResponse,
    ScheduledPost,
)
from .store import GalleryStore
from .vision import ensure_vision

# Module-level rotation tracker (swap for Redis in multi-worker prod).
_rotation = RotationTracker()

# 2026 UGC hashtag pools — niche-first, not spammy.
DEFAULT_HASHTAG_BANK = [
    "#legday",
    "#gymgirl",
    "#mealprep",
    "#miami",
    "#tryonhaul",
    "#cleaneating",
    "#fitspo",
    "#grwm",
]

PILLAR_ROTATION = ["gym", "outfit", "food", "lifestyle", "gym", "outfit"]


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def _assets_block(assets: list[GalleryAsset]) -> str:
    lines = []
    for a in assets:
        tags = ", ".join(a.tags) if a.tags else "none"
        vision = a.vision_summary or "(not yet analyzed — run /gallery/analyze)"
        vibe = a.vibe or "unknown"
        vtags = ", ".join(a.visual_tags) if a.visual_tags else "none"
        pair = ", ".join(a.pairing_hints) if a.pairing_hints else "none"
        lines.append(
            f"  - id={a.id!r} kind={a.kind} pillar={a.pillar}\n"
            f"      VIBE: {vibe!r}\n"
            f"      SEES: {vision}\n"
            f"      visual_tags=[{vtags}] pairing_hints=[{pair}]\n"
            f"      suggested_lane={a.suggested_lane} suggested_type={a.suggested_type}\n"
            f"      human_hint={a.description!r} tags=[{tags}]"
        )
    return "\n".join(lines) if lines else "  (empty gallery)"


def _schedule_dates(days: int) -> list[str]:
    today = date.today()
    return [(today + timedelta(days=i)).isoformat() for i in range(days)]


async def curate(req: CurateRequest, persona_key: str = "lorena") -> CurateResponse:
    """Plan a batch of posts from the cloud gallery — 2026 UGC director mode."""
    store = GalleryStore()
    manifest = store.load()
    assets = [a for a in manifest.assets if not a.posted]

    if not assets:
        return CurateResponse(
            posting_queue=[],
            strategy_notes="Gallery is empty or everything is already posted. Upload new clips to S3.",
            warnings=["no_unposted_assets"],
        )

    vision_warnings: list[str] = []
    if req.refresh_vision:
        assets, vision_warnings = await ensure_vision(
            assets, store, force=False, persona_key=persona_key
        )

    assets, rag_warnings, rag_hits = await retrieve_assets_for_curation(
        assets,
        notes=req.notes,
        days_ahead=req.days_ahead,
        max_posts_per_day=req.max_posts_per_day,
    )

    persona = get_persona(persona_key)
    llm = get_llm()
    dates = _schedule_dates(req.days_ahead)
    cooldown_hint = ""
    blocked = _rotation.recent_staples()
    if blocked:
        cooldown_hint = f"\nPhrases on cooldown (do NOT reuse): {blocked[:8]}\n"

    user = (
        "RETURN_CURATE_JSON\n"
        "You are a 2026 UGC director for @itslorenamor. From the gallery below, build a posting plan.\n"
        "You have SEEN each asset (vision_summary + vibe). Group by visual vibe and pairing_hints.\n"
        "Rules:\n"
        "- Group assets that FIT TOGETHER (same vibe/day: leg day batch, outfit try-ons, meal prep).\n"
        "- Carousels: 2-4 slides max, one theme per carousel.\n"
        "- Reels: one strong hook each; vary lanes A/B/D/E across the week.\n"
        "- Space pillars: don't post 3 gym reels back-to-back.\n"
        f"- Max {req.max_posts_per_day} posts per day for {req.days_ahead} days.\n"
        "- Captions: Lorena voice, <=22 words, smug not sweet, one concrete detail each.\n"
        "- Hashtags: 3-5 per post, niche-first (#legday #mealprep not #love #instagood).\n"
        "- Every caption ends with CTA style matching cta 1/2/3.\n"
        "- Set approval_required true on every post.\n"
        f"{cooldown_hint}"
        f"Available dates: {dates}\n"
        f"Notes: {req.notes or 'none'}\n\n"
        "GALLERY (unposted — RAG-selected subset; includes what the vision model SAW):\n"
        f"{_assets_block(assets)}\n\n"
        "Respond with JSON keys:\n"
        "  posting_queue: list of {asset_ids, format, lane, type, cta, code, on_screen_text, "
        "caption, hashtags, scheduled_date, pillar, pairing_reason}\n"
        "  carousel_groups: list of {group_id, asset_ids, theme, caption, hashtags}\n"
        "  bio_suggestion (optional string)\n"
        "  hashtag_bank: refreshed list of 8-12 tags for the week\n"
        "  strategy_notes: 2-3 sentences on the week's vibe arc\n"
    )

    raw = await llm.chat(
        [ChatMessage("system", persona.system_prompt), ChatMessage("user", user)],
        json_mode=True,
        max_tokens=2048,
    )
    data = _extract_json(raw)

    queue: list[ScheduledPost] = []
    for item in data.get("posting_queue", []):
        caption = safety.sanitize_dialogue(str(item.get("caption", "")))
        _rotation.record([caption])
        queue.append(
            ScheduledPost(
                asset_ids=list(item.get("asset_ids", [])),
                format=item.get("format", "reel"),
                lane=str(item.get("lane", "A")),
                type=str(item.get("type", "silent")),
                cta=int(item.get("cta", 1)),
                code=str(item.get("code", "")),
                on_screen_text=str(item.get("on_screen_text", "")).upper(),
                caption=caption,
                hashtags=[str(h) for h in item.get("hashtags", [])][:5],
                scheduled_date=str(item.get("scheduled_date", dates[0])),
                pillar=item.get("pillar", "other"),
                approval_required=True,
                pairing_reason=str(item.get("pairing_reason", "")),
            )
        )

    carousels = [
        CarouselGroup(
            group_id=str(g.get("group_id", f"g{i}")),
            asset_ids=list(g.get("asset_ids", [])),
            theme=str(g.get("theme", "")),
            caption=safety.sanitize_dialogue(str(g.get("caption", ""))),
            hashtags=[str(h) for h in g.get("hashtags", [])][:5],
        )
        for i, g in enumerate(data.get("carousel_groups", []))
    ]

    bio = data.get("bio_suggestion") if req.include_bio_update else None
    if bio:
        bio = safety.sanitize_dialogue(str(bio))

    comment_replies = await _draft_comment_replies(req.pending_comments, persona_key)

    bank = [str(h) for h in data.get("hashtag_bank", DEFAULT_HASHTAG_BANK)]
    warnings: list[str] = []
    for post in queue:
        warnings.extend(safety.audit(post.caption))
    warnings = vision_warnings + rag_warnings + warnings

    return CurateResponse(
        posting_queue=queue,
        carousel_groups=carousels,
        bio_suggestion=bio,
        comment_replies=comment_replies,
        hashtag_bank=bank,
        strategy_notes=str(data.get("strategy_notes", "")),
        rag_hits=rag_hits,
        warnings=list(dict.fromkeys(warnings)),
    )


async def _draft_comment_replies(
    comments: list[CommentToReply],
    persona_key: str,
) -> list[CommentReplyDraft]:
    if not comments:
        return []
    persona = get_persona(persona_key)
    llm = get_llm()
    drafts: list[CommentReplyDraft] = []
    for c in comments:
        user = (
            "RETURN_COMMENT_REPLY\n"
            "Write ONE short Instagram comment reply (<=18 words) in Lorena's voice. "
            "Sassy, not sweet. No hashtags.\n\n"
            f"Comment by @{c.author}: {c.text!r}\n"
            f"Post context: {c.context or 'general'}"
        )
        raw = await llm.chat(
            [ChatMessage("system", persona.system_prompt), ChatMessage("user", user)],
            max_tokens=60,
        )
        reply = safety.sanitize_dialogue(raw.strip())
        drafts.append(
            CommentReplyDraft(
                comment_id=c.comment_id,
                post_id=c.post_id,
                reply=reply,
            )
        )
    return drafts


async def reply_to_comment(req: ReplyRequest, persona_key: str = "lorena") -> ReplyResponse:
    drafts = await _draft_comment_replies([req.comment], persona_key)
    if not drafts:
        return ReplyResponse(reply="", warnings=["empty"])
    d = drafts[0]
    return ReplyResponse(reply=d.reply, warnings=safety.audit(d.reply))
