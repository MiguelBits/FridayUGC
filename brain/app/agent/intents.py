"""High-level intent vocabulary — brain plans behavior, phone resolves motor."""

from __future__ import annotations

INTENT_NAMES = frozenset({
    "enter_reels",
    "watch_reel",
    "open_comments",
    "engage_comments",
    "next_reel",
    "browse_feed",
    "go_back",
    "check_inbox",
    "open_profile",
    "dwell",
})

INTENT_SPEC = """
INTENT-FIRST PLANNING (preferred over atomic tap/swipe when on Instagram):
Return {"action":"intent","params":{"name":"<intent>", ...optional...}} and the phone
translates to human motor actions at execution time (fresh UI binding).

Intents:
- enter_reels — reach reels_viewer from any Instagram screen (phone tries nav, pager swipe, memory).
- watch_reel — dwell on current reel; params: dwell_ms (1500–8000, vary by content).
- open_comments — open comments sheet on current reel (vision/a11y/memory, no hardcoded coords).
- engage_comments — like next comment heart when on comments_sheet.
- next_reel — swipe up to next reel with human motor variation.
- browse_feed — scroll home feed; params: direction (up|down), dwell_ms optional.
- go_back — press Android back.
- check_inbox — navigate to inbox/DMs tab.
- open_profile — navigate to profile tab.
- dwell — human pause; params: dwell_ms (500–6000).

Use atomic actions (tap, swipe, navigate) only when you have a concrete target_id or
screenshot-grounded x,y from SCREEN ELEMENTS. Prefer intents for navigation and reels work.
"""
