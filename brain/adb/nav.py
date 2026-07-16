"""Instagram bottom navigation tab coordinates."""

from __future__ import annotations

# Current IG (tall phones / PT-PT probe 1440x3216):
#   Home | Search | Reels | Shop | Profile  — Reels is CENTER (~0.50).
# Legacy layout still seen on some builds:
#   Home | Reels | Create | Search | Profile — Reels second (~0.30).
IG_NAV_X: dict[str, float] = {
    "home": 0.10,
    "search": 0.30,
    "reels": 0.50,
    "shop": 0.70,
    "inbox": 0.70,
    "activity": 0.70,
    "profile": 0.90,
    "create": 0.50,
}

# Prefer center Reels, then legacy second-tab.
REELS_X_CANDIDATES: tuple[float, ...] = (0.50, 0.30)

# Tall phones (e.g. 1440x3216): 0.978 lands in the system gesture bar and misses tabs.
NAV_Y_FRAC = 0.965
NAV_Y_FRAC_TALL = 0.955
TALL_ASPECT = 2.1


def is_tall_phone(screen_width: int, screen_height: int) -> bool:
    return screen_height > 0 and screen_width > 0 and (screen_height / screen_width) >= TALL_ASPECT


def nav_y_frac(screen_width: int, screen_height: int) -> float:
    if is_tall_phone(screen_width, screen_height):
        return NAV_Y_FRAC_TALL
    return NAV_Y_FRAC


def nav_xy(tab: str, screen_width: int, screen_height: int) -> tuple[int, int]:
    frac = IG_NAV_X.get(tab, IG_NAV_X["home"])
    x = int(screen_width * frac)
    y = int(screen_height * nav_y_frac(screen_width, screen_height))
    return x, y


def nav_y_candidates(screen_height: int, screen_width: int = 1080) -> list[float]:
    """Y fractions to retry when Reels entry fails."""
    if is_tall_phone(screen_width, screen_height):
        return [0.955, 0.945, 0.935, 0.965]
    return [0.965, 0.955, 0.978]


def nav_reels_candidates(screen_width: int, screen_height: int) -> list[tuple[int, int, float, float]]:
    """(x, y, x_frac, y_frac) attempts for Reels tab — center-first, then legacy X."""
    out: list[tuple[int, int, float, float]] = []
    for x_frac in REELS_X_CANDIDATES:
        for y_frac in nav_y_candidates(screen_height, screen_width):
            out.append(
                (
                    int(screen_width * x_frac),
                    int(screen_height * y_frac),
                    x_frac,
                    y_frac,
                )
            )
    return out
