from __future__ import annotations

from .actions import Screen, ScreenState, StepRequest

# Screen types — app-agnostic vocabulary; Instagram maps into these.
SCREEN_TYPES = frozenset({
    "unknown",
    "other_app",
    "launcher",
    "home_feed",
    "reels_viewer",
    "comments_sheet",
    "inbox",
    "profile",
    "search",
    "story_viewer",
    "create_flow",
    "dialog",
})

TAB_NAMES = frozenset({"unknown", "home", "reels", "search", "profile", "inbox", "create"})


def has_home_feed_tabs(screen: Screen) -> bool:
    """True when Instagram home-feed tab labels are visible — not reels_viewer."""
    for e in screen.elements:
        t = e.text.lower()
        if "for you" in t or "following" in t:
            return True
    return False


def _texts(screen: Screen) -> list[str]:
    return [e.text.lower() for e in screen.elements]


def has_comments_sheet_signals(screen: Screen) -> bool:
    texts = _texts(screen)
    if any("reply" in t for t in texts):
        return True
    if any("view" in t and "comment" in t for t in texts):
        return True
    if any("view all" in t for t in texts):
        return True
    has_composer = any("add comment" in t or "add a comment" in t for t in texts)
    if has_composer and len(screen.elements) >= 8:
        return True
    if any("comments" in t and "selected" not in t for t in texts) and len(screen.elements) >= 6:
        return True
    return False


def is_reel_overlay_composer_only(screen: Screen, activity: str = "") -> bool:
    texts = _texts(screen)
    has_composer = any("add comment" in t or "add a comment" in t for t in texts)
    if not has_composer:
        return False
    activity_lower = (activity or screen.activity or "").lower()
    on_reels = "clips" in activity_lower or ("reel" in activity_lower and "profile" not in activity_lower)
    if not on_reels:
        return False
    return not has_comments_sheet_signals(screen)


def is_full_comments_sheet(screen: Screen, activity: str = "") -> bool:
    if is_reel_overlay_composer_only(screen, activity):
        return False
    return has_comments_sheet_signals(screen)


def classify_screen(screen: Screen, screen_state: ScreenState | None = None) -> ScreenState:
    """Use phone-provided state when present; otherwise infer from tree (legacy)."""
    if screen_state and screen_state.screen_type != "unknown":
        return screen_state
    if screen_state:
        base = screen_state
    else:
        base = ScreenState()

    pkg = (screen.app or "").lower()
    texts = [e.text.lower() for e in screen.elements]
    signals = list(base.signals)

    if not pkg or "instagram" not in pkg:
        return ScreenState(
            app_package=screen.app,
            activity_class=screen.activity or base.activity_class,
            screen_type="other_app" if pkg else "unknown",
            selected_tab="unknown",
            confidence=0.9 if pkg else 0.2,
            element_count=len(screen.elements),
            signals=signals or ["not Instagram"],
            needs_vision=True,
        )

    if any("for you" in t or "following" in t for t in texts):
        return ScreenState(
            app_package=screen.app,
            activity_class=screen.activity,
            screen_type="home_feed",
            selected_tab="home",
            confidence=max(base.confidence, 0.88),
            element_count=len(screen.elements),
            signals=signals + ["home feed tabs"],
            needs_vision=len(screen.elements) < 10,
        )

    if is_full_comments_sheet(screen, screen.activity):
        return ScreenState(
            app_package=screen.app,
            activity_class=screen.activity,
            screen_type="comments_sheet",
            selected_tab=base.selected_tab,
            confidence=max(base.confidence, 0.88),
            element_count=len(screen.elements),
            signals=signals + ["comments sheet open"],
            needs_vision=False,
        )

    activity = (screen.activity or base.activity_class or "").lower()
    if ("clips" in activity or ("reel" in activity and "profile" not in activity)) and not has_home_feed_tabs(screen):
        big = [e for e in screen.elements if e.scrollable and e.h > 400 and e.w > 200]
        if big or len(screen.elements) < 15:
            return ScreenState(
                app_package=screen.app,
                activity_class=screen.activity,
                screen_type="reels_viewer",
                selected_tab="reels",
                confidence=max(base.confidence, 0.82),
                element_count=len(screen.elements),
                signals=signals + ["reels activity"],
                needs_vision=len(screen.elements) < 8,
            )

    big = [e for e in screen.elements if e.scrollable and e.h > 400 and e.w > 200]
    activity = (screen.activity or base.activity_class or "").lower()
    activity_suggests_reels = "clips" in activity or ("reel" in activity and "profile" not in activity)
    if big and len(screen.elements) < 15 and activity_suggests_reels:
        return ScreenState(
            app_package=screen.app,
            activity_class=screen.activity,
            screen_type="reels_viewer",
            selected_tab="reels",
            confidence=max(base.confidence, 0.8),
            element_count=len(screen.elements),
            signals=signals + ["reels activity + sparse scrollable"],
            needs_vision=len(screen.elements) < 8,
        )
    if big and len(screen.elements) < 15:
        return ScreenState(
            app_package=screen.app,
            activity_class=screen.activity,
            screen_type="home_feed",
            selected_tab="home",
            confidence=min(max(base.confidence, 0.5), 0.6),
            element_count=len(screen.elements),
            signals=signals + ["sparse scrollable feed — not reels without session"],
            needs_vision=True,
        )

    return base.model_copy(
        update={
            "app_package": screen.app,
            "activity_class": screen.activity or base.activity_class,
            "element_count": len(screen.elements),
            "needs_vision": base.needs_vision or base.confidence < 0.55 or len(screen.elements) < 8,
        }
    )


def is_reels_viewer(state: ScreenState) -> bool:
    return state.screen_type == "reels_viewer" and state.confidence >= 0.55


def on_reels_surface(
    state: ScreenState,
    ctx: dict | None = None,
    screen: Screen | None = None,
) -> bool:
    """True only on a confirmed Reels/comments surface — never trust reels_tab_opened alone."""
    _ = ctx  # session flag is advisory; classifier + tree win
    if screen and has_home_feed_tabs(screen):
        return False
    if state.screen_type == "comments_sheet":
        return True
    if is_reels_viewer(state):
        return True
    activity = (state.activity_class or "").lower()
    if "clips" in activity or ("reel" in activity and "profile" not in activity):
        return state.screen_type not in {"home_feed", "story_viewer", "other_app", "launcher"}
    return False


def is_story_viewer(state: ScreenState) -> bool:
    return state.screen_type == "story_viewer"


def is_home_feed(state: ScreenState) -> bool:
    return state.screen_type == "home_feed"


def screen_state_block(state: ScreenState) -> str:
    sig = ", ".join(state.signals[:6]) if state.signals else "none"
    return (
        f"SCREEN_STATE (trust this over guessing from one label):\n"
        f"  app={state.app_package or 'unknown'}\n"
        f"  activity={state.activity_class or 'unknown'}\n"
        f"  screen_type={state.screen_type}\n"
        f"  selected_tab={state.selected_tab}\n"
        f"  confidence={state.confidence:.2f}\n"
        f"  elements={state.element_count}\n"
        f"  signals={sig}\n"
        f"  needs_vision={str(state.needs_vision).lower()}\n"
    )


def on_comments_sheet(state: ScreenState, ctx: dict | None = None) -> bool:
    if state.screen_type == "comments_sheet":
        return True
    if not ctx:
        return False
    try:
        opened = int(ctx.get("comments_sheet_open", 0))
    except (TypeError, ValueError):
        opened = 0
    return opened == 1 and state.screen_type not in {"story_viewer", "other_app", "launcher"}


def resolve_state(req: StepRequest) -> ScreenState:
    state = classify_screen(req.screen, req.screen_state)
    if has_home_feed_tabs(req.screen) and state.screen_type in {"reels_viewer", "unknown"}:
        signals = list(state.signals) + ["home feed tabs visible — not reels_viewer"]
        state = state.model_copy(
            update={
                "screen_type": "home_feed",
                "selected_tab": "home",
                "confidence": min(state.confidence, 0.65),
                "signals": signals,
                "needs_vision": True,
            }
        )
    ctx = req.session_context or {}
    try:
        opened = int(ctx.get("reels_tab_opened", 0))
    except (TypeError, ValueError):
        opened = 0
    activity = (state.activity_class or "").lower()
    strong_reels = "clips" in activity or ("reel" in activity and "profile" not in activity)
    if opened == 0 and state.screen_type == "reels_viewer" and not strong_reels:
        signals = list(state.signals) + ["reels_tab_opened=0 — downgrade to home_feed"]
        state = state.model_copy(
            update={
                "screen_type": "home_feed",
                "selected_tab": "home",
                "confidence": min(state.confidence, 0.6),
                "signals": signals,
                "needs_vision": True,
            }
        )
    if opened == 1 and state.screen_type in {"home_feed", "unknown"} and not has_home_feed_tabs(req.screen):
        activity = (state.activity_class or "").lower()
        strong_reels = "clips" in activity or ("reel" in activity and "profile" not in activity)
        if strong_reels and state.screen_type != "home_feed":
            signals = list(state.signals) + ["reels_tab_opened — override to reels_viewer"]
            return state.model_copy(
                update={
                    "screen_type": "reels_viewer",
                    "selected_tab": "reels",
                    "confidence": max(state.confidence, 0.78),
                    "signals": signals,
                }
            )
    try:
        comments_open = int(ctx.get("comments_sheet_open", 0))
    except (TypeError, ValueError):
        comments_open = 0
    if comments_open == 1 and state.screen_type not in {"comments_sheet", "story_viewer", "other_app"}:
        signals = list(state.signals) + ["comments_sheet_open — override to comments_sheet"]
        return state.model_copy(
            update={
                "screen_type": "comments_sheet",
                "selected_tab": "reels",
                "confidence": max(state.confidence, 0.8),
                "signals": signals,
            }
        )
    return state
