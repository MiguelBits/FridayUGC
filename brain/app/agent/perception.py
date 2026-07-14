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

    if any("add a comment" in t for t in texts):
        return ScreenState(
            app_package=screen.app,
            activity_class=screen.activity,
            screen_type="comments_sheet",
            selected_tab=base.selected_tab,
            confidence=max(base.confidence, 0.85),
            element_count=len(screen.elements),
            signals=signals + ["comment sheet"],
            needs_vision=False,
        )

    big = [e for e in screen.elements if e.scrollable and e.h > 400 and e.w > 200]
    if big and len(screen.elements) < 15:
        return ScreenState(
            app_package=screen.app,
            activity_class=screen.activity,
            screen_type="reels_viewer",
            selected_tab="reels",
            confidence=max(base.confidence, 0.75),
            element_count=len(screen.elements),
            signals=signals + ["sparse reel surface"],
            needs_vision=len(screen.elements) < 8,
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


def on_reels_surface(state: ScreenState, ctx: dict | None = None) -> bool:
    if is_reels_viewer(state):
        return True
    if not ctx:
        return False
    try:
        opened = int(ctx.get("reels_tab_opened", 0))
    except (TypeError, ValueError):
        opened = 0
    if opened != 1:
        return False
    # Preflight swipe-left lands on Reels but classifier often still says home_feed.
    return state.screen_type not in {"story_viewer", "other_app", "launcher"}


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
    ctx = req.session_context or {}
    try:
        opened = int(ctx.get("reels_tab_opened", 0))
    except (TypeError, ValueError):
        opened = 0
    if opened == 1 and state.screen_type in {"home_feed", "unknown"}:
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
