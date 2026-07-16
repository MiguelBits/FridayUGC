"""Instagram bottom navigation tab coordinates."""

from __future__ import annotations

# Current IG layout (5 tabs, left → right): Home | Reels | DMs | Search | Profile
IG_NAV_X: dict[str, float] = {
    "home": 0.10,
    "reels": 0.30,
    "inbox": 0.50,
    "activity": 0.50,
    "search": 0.70,
    "profile": 0.90,
    "create": 0.50,
}

# Tab bar sits at the very bottom — 94% hits feed posts on tall screens.
NAV_Y_FRAC = 0.978


def nav_xy(tab: str, screen_width: int, screen_height: int) -> tuple[int, int]:
    frac = IG_NAV_X.get(tab, IG_NAV_X["home"])
    x = int(screen_width * frac)
    y = int(screen_height * NAV_Y_FRAC)
    return x, y
