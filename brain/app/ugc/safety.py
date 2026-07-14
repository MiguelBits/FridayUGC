from __future__ import annotations

import re

# Visual-prompt banned terms -> platform-safe replacement (from DIRECTOR_FLOW "Banned in prompts").
VISUAL_SWAPS: dict[str, str] = {
    "collarbone": "neckline",
    "cleavage": "neckline",
    "bare skin": "fully clothed",
    "chest": "neckline",
    "thighs": "legs (fully clothed)",
    "bodycon": "fitted midi dress",
    "keyhole": "ring detail",
    "lingerie": "fitted top",
    "seductive": "confident",
    "intimate": "direct",
    "sheer": "opaque",
    "see-through": "opaque",
    "translucent": "opaque",
    "mesh": "opaque fabric",
    "snatch frame": "slow push-in",
}

# Dialogue banned terms -> replacement (from DIRECTOR_FLOW "Banned in dialogue").
DIALOGUE_SWAPS: dict[str, str] = {
    "good boy": "good dog",
    "snatches": "fits tight",
    "snatch": "fits tight",
    "gape": "stay flat",
    "keyhole": "ring detail",
    "unhinged": "chaotic",
    "almost whispers": "speaks clearly",
    "whispers softly": "speaks softly",
}

# Filler that should never appear in any audience-facing copy.
BANNED_FILLER: tuple[str, ...] = (
    "vibe check",
    "algorithm",
    "quiet luxury",
    "ootd check",
    "you won't believe",
    "works every time",
)

# Device wording banned in visual prompts (phone-safe rule).
DEVICE_BANNED: tuple[str, ...] = (
    "iphone",
    "phone in hand",
    "mirror shows phone",
    "adjusts phone angle",
    "turns back to phone",
)


def _swap(text: str, mapping: dict[str, str]) -> str:
    out = text
    for bad, good in mapping.items():
        out = re.sub(rf"\b{re.escape(bad)}\b", good, out, flags=re.IGNORECASE)
    return out


def sanitize_visual(prompt: str) -> str:
    """Make a generation (Seedance / Marketing Studio) prompt platform-safe."""
    return _swap(prompt, VISUAL_SWAPS)


def sanitize_dialogue(text: str) -> str:
    """Make spoken/caption/comment copy platform-safe."""
    return _swap(text, DIALOGUE_SWAPS)


def audit(text: str) -> list[str]:
    """Return a list of safety warnings for text (does not modify it)."""
    warnings: list[str] = []
    low = text.lower()
    for term in BANNED_FILLER:
        if term in low:
            warnings.append(f"banned filler: {term!r}")
    for term in DEVICE_BANNED:
        if term in low:
            warnings.append(f"device wording (phone-safe rule): {term!r}")
    for bad in {**VISUAL_SWAPS, **DIALOGUE_SWAPS}:
        if re.search(rf"\b{re.escape(bad)}\b", low):
            warnings.append(f"unsafe term: {bad!r}")
    return warnings
