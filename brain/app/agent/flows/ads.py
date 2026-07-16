"""Detect Instagram sponsored Reels / feed ads — swipe away, never engage."""

from __future__ import annotations

from ..actions import Screen

# PT + EN markers. Organic reels show remix/repost affordances; ads show these instead.
AD_TEXT_HINTS = (
    "patrocinado",
    "sponsored",
    "ver detalhes",
    "see details",
    "shop now",
    "comprar agora",
    "saiba mais",
    "learn more",
    "instalar",
    "install now",
    "enviar mensagem",
    "send message",
    "cookie settings",
    "reject all",
    "accept all",
)

# In-app browser / lead-form traps (not comments).
TRAP_TEXT_HINTS = (
    "cookie settings",
    "reject all",
    "accept all",
    "continuar",
    "betterhelp",
    "e-mail",
    "número de telefone",
    "customize my choices",
)

HOME_FEED_HINTS = (
    "para ti",
    "for you",
    "following",
    "a seguir",
    "a tua história",
    "your story",
)

COMMENTS_TITLE_HINTS = (
    "comentários",
    "comments",
    "add a comment",
    "adicionar um comentário",
    "reply",
    "responder",
)

# Organic Reels often expose remix/repost on the rail or overflow; ads usually don't.
ORGANIC_REEL_HINTS = (
    "remix",
    "republish",
    "repost",
    "republicar",
    "reutilizar",
)


def _joined_texts(screen: Screen, extra_texts: list[str] | None = None) -> str:
    parts = [e.text.lower() for e in screen.elements if e.text]
    if extra_texts:
        parts.extend(t.lower() for t in extra_texts if t)
    return " ".join(parts)


def is_home_feed_surface(screen: Screen, extra_texts: list[str] | None = None) -> bool:
    joined = _joined_texts(screen, extra_texts)
    return any(h in joined for h in HOME_FEED_HINTS)


def is_sponsored_ad(screen: Screen, extra_texts: list[str] | None = None) -> bool:
    """True when this publication is an ad — swipe away, do not open comments."""
    joined = _joined_texts(screen, extra_texts)
    if any(h in joined for h in AD_TEXT_HINTS):
        return True
    # User rule: if reel UI has no remix/repost/republish signal and shows CTA-ish copy, treat as ad.
    # Only apply when we have some UI text (uiautomator) so we don't false-positive empty trees.
    if joined and not any(h in joined for h in ORGANIC_REEL_HINTS):
        if "seguir" in joined and ("ver detalhes" in joined or "www." in joined):
            return True
    return False


def is_trap_overlay(screen: Screen, extra_texts: list[str] | None = None) -> bool:
    """Cookie banners, lead forms, in-app browsers — press back, not comments success."""
    joined = _joined_texts(screen, extra_texts)
    hits = sum(1 for h in TRAP_TEXT_HINTS if h in joined)
    return hits >= 2 or "cookie settings" in joined


def looks_like_comments_sheet(screen: Screen, extra_texts: list[str] | None = None) -> bool:
    joined = _joined_texts(screen, extra_texts)
    if is_trap_overlay(screen, extra_texts):
        return False
    if is_sponsored_ad(screen, extra_texts) and not any(h in joined for h in COMMENTS_TITLE_HINTS):
        return False
    return any(h in joined for h in COMMENTS_TITLE_HINTS)
