"""Predefined Instagram action flows (deterministic choreography)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FlowStep:
    id: str
    kind: str  # motor | ground_tap | wait | evaluate
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    anchor: str = ""
    expect_surface: str = ""  # reels_viewer | comments_sheet | ...
    say: str = ""
    reason: str = ""


@dataclass(frozen=True)
class FlowDef:
    id: str
    title: str
    doc: str
    steps: tuple[FlowStep, ...]


# Right-rail comments: between reel-like and share. Tall phones push the rail lower.
COMMENTS_ICON_X_FRAC = 0.90
COMMENTS_ICON_Y_FRAC = 0.52
# Probe offsets around the aspect-aware base (learned from 1440x3216 device).
COMMENTS_ICON_Y_OFFSETS = (0.00, 0.03, -0.02, 0.05, -0.04, 0.07)

# Band for vision acceptance — share sits below comments; tall phones need more room.
COMMENTS_BAND_Y_MIN = 0.48
COMMENTS_BAND_Y_MAX = 0.62
COMMENTS_BAND_SHARE_FLOOR = 0.64
COMMENTS_BAND_X_MIN = 0.78


def comments_y_frac_for_screen(screen_width: int, screen_height: int) -> float:
    """Base Y for comments icon — lower on very tall displays (e.g. 1440x3216)."""
    _ = screen_width
    if screen_height <= 0:
        return COMMENTS_ICON_Y_FRAC
    # Probe device was 3216px tall; rail icons sit lower than on 2400px mocks.
    if screen_height >= 3000:
        return 0.58
    if screen_height >= 2800:
        return 0.55
    return COMMENTS_ICON_Y_FRAC


def comments_icon_xy(
    screen_width: int,
    screen_height: int,
    *,
    y_frac: float | None = None,
) -> tuple[int, int]:
    y = comments_y_frac_for_screen(screen_width, screen_height) if y_frac is None else y_frac
    return int(screen_width * COMMENTS_ICON_X_FRAC), int(screen_height * y)


FLOW_OPEN_REELS = FlowDef(
    id="open_reels",
    title="Open Instagram Reels",
    doc="docs/flows/OPEN_REELS.md",
    steps=(
        FlowStep(
            id="navigate_reels",
            kind="motor",
            action="navigate",
            params={"tab": "reels", "ui_key": "nav_reels"},
            expect_surface="reels_viewer",
            say="Opening Reels.",
            reason="flow open_reels navigate",
        ),
    ),
)

FLOW_OPEN_COMMENTS = FlowDef(
    id="open_comments",
    title="Open Reels comments sheet",
    doc="docs/flows/OPEN_COMMENTS.md",
    steps=(
        FlowStep(
            id="tap_comments_icon",
            kind="ground_tap",
            action="tap",
            anchor="comments_icon",
            params={"ui_key": "comments_icon"},
            expect_surface="comments_sheet",
            say="Open comments.",
            reason="flow open_comments tap comments_icon",
        ),
        FlowStep(
            id="evaluate_comments",
            kind="evaluate",
            expect_surface="comments_sheet",
            reason="flow open_comments evaluate surface",
        ),
    ),
)

FLOWS: dict[str, FlowDef] = {
    FLOW_OPEN_REELS.id: FLOW_OPEN_REELS,
    FLOW_OPEN_COMMENTS.id: FLOW_OPEN_COMMENTS,
}
