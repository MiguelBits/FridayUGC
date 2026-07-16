"""Tests for POST /agent/tick thin-client loop."""

from __future__ import annotations

import asyncio

import pytest

from app.agent.actions import ObserveBundle, Screen, TickLastResult, TickRequest
from app.agent.routines import apply_verified_action, comment_likes_plan
from app.agent.session_store import SessionStore
from app.agent.tick import handle_tick
from app.agent.verifier import verify_last


@pytest.fixture
def reels_comment_likes_ctx():
    return {
        "phase": "reels_comment_likes",
        "comment_likes_phase": "on_reels",
        "comment_likes_used": 0,
        "comment_likes_max": 50,
        "comment_likes_per_reel": 5,
        "reels_tab_opened": 1,
    }


def test_tick_comment_likes_opens_comments(monkeypatch, tmp_path, reels_comment_likes_ctx):
    db = tmp_path / "tick.db"
    store = SessionStore(str(db))
    monkeypatch.setattr("app.agent.tick._store", store)

    async def fake_ground(req):
        from app.agent.actions import GroundResponse

        return GroundResponse(action="tap", params={"x": 100, "y": 200}, confidence=0.9)

    monkeypatch.setattr("app.agent.grounding.ground_target", fake_ground)

    screen = Screen(
        app="com.instagram.android",
        activity="ReelViewerActivity",
        elements=[{"id": 0, "text": "Reels", "role": "button"}],
    )
    req = TickRequest(
        session_id="tick-test-1",
        device_id="dev-1",
        goal="Like comments on reels",
        step=0,
        observe=ObserveBundle(screen=screen, screen_width=1080, screen_height=2400),
        session_context=reels_comment_likes_ctx,
    )
    resp = asyncio.run(handle_tick(req))
    assert resp.action in {"tap", "wait", "swipe"}
    assert resp.session_context["phase"] == "reels_comment_likes"


def test_verify_comments_icon_opens_sheet():
    before = Screen(app="com.instagram.android", activity="ReelViewerActivity", elements=[])
    after = Screen(
        app="com.instagram.android",
        activity="CommentsActivity",
        elements=[{"id": 0, "text": "Reply", "role": "button", "y": 800}],
    )
    result = TickLastResult(
        action="tap",
        executor_ok=True,
        ui_key="comments_icon",
        before_observe=ObserveBundle(screen=before),
        after_observe=ObserveBundle(screen=after),
    )
    verified, score = verify_last(result, after.activity)
    assert verified in {"verified", "unverified"}


def test_comment_likes_starts_with_deeplink():
    from app.agent.perception import classify_screen

    ctx = {
        "phase": "reels_comment_likes",
        "comment_likes_phase": "on_reels",
        "reels_tab_opened": 0,
        "reels_entry_attempts": 0,
    }
    screen = Screen(
        app="com.instagram.android",
        activity="MainActivity",
        elements=[{"id": 0, "text": "Home", "role": "button"}],
    )
    plan = comment_likes_plan(ctx, screen, classify_screen(screen))
    assert plan is not None
    assert plan.kind == "motor"
    assert plan.action == "navigate"
    assert plan.params.get("tab") == "reels"


def test_apply_navigate_unverified_still_opens_reels_flag():
    ctx = {"reels_tab_opened": 0, "reels_entry_attempts": 0}
    apply_verified_action(ctx, "navigate", "unverified", {"tab": "reels"}, executor_ok=True)
    assert ctx["reels_tab_opened"] == 1
    assert ctx["reels_entry_attempts"] == 1


def test_comment_likes_budget_done():
    from app.agent.perception import classify_screen

    ctx = {
        "phase": "reels_comment_likes",
        "comment_likes_used": 50,
        "comment_likes_max": 50,
    }
    screen = Screen(app="com.instagram.android", activity="ReelViewerActivity")
    plan = comment_likes_plan(ctx, screen, classify_screen(screen))
    assert plan is not None
    assert plan.kind == "done"


def test_comment_likes_cycle_on_reels():
    from app.agent.perception import classify_screen

    ctx = {
        "phase": "reels_comment_likes",
        "comment_likes_phase": "on_reels",
        "reels_tab_opened": 1,
        "reels_scrolled": 0,
        "reel_dwell_done": 0,
    }
    screen = Screen(
        app="com.instagram.android",
        activity="com.instagram.clips.viewer.ClipsViewerFragment",
        elements=[],
    )
    state = classify_screen(screen)
    plan = comment_likes_plan(ctx, screen, state)
    assert plan is not None
    assert plan.kind == "motor"
    assert plan.action == "wait"
    assert ctx["reel_dwell_done"] == 1
    assert 2 <= ctx["comment_likes_this_reel_target"] <= 5

    plan = comment_likes_plan(ctx, screen, state)
    assert plan.kind == "ground_tap"
    assert plan.anchor == "comments_icon"


def test_comment_likes_skips_nav_retry_after_tab_opened():
    from app.agent.perception import classify_screen

    ctx = {
        "phase": "reels_comment_likes",
        "comment_likes_phase": "on_reels",
        "reels_tab_opened": 1,
        "reels_entry_attempts": 1,
        "reel_dwell_done": 0,
    }
    screen = Screen(
        app="com.instagram.android",
        activity="MainActivity",
        elements=[],
    )
    plan = comment_likes_plan(ctx, screen, classify_screen(screen))
    assert plan is not None
    assert plan.action == "wait"
    assert plan.kind == "motor"


def test_comment_likes_close_then_next_reel():
    from app.agent.perception import classify_screen

    ctx = {
        "phase": "reels_comment_likes",
        "comment_likes_phase": "on_reels",
        "reels_tab_opened": 1,
        "reels_scrolled": 1,
        "ready_for_next_reel": 1,
        "reels_max": 10,
    }
    screen = Screen(
        app="com.instagram.android",
        activity="com.instagram.clips.viewer.ClipsViewerFragment",
    )
    plan = comment_likes_plan(ctx, screen, classify_screen(screen))
    assert plan is not None
    assert plan.action == "swipe"
    assert plan.params["zone"] == "reels_rail"


def test_apply_back_then_swipe_resets_for_next_reel():
    ctx = {
        "comments_sheet_open": 1,
        "comment_likes_this_reel": 3,
        "comment_likes_phase": "in_comments",
        "comment_likes_this_reel_target": 3,
    }
    apply_verified_action(ctx, "press", "unknown", {"key": "back"}, executor_ok=True)
    assert ctx["ready_for_next_reel"] == 1
    assert ctx["comments_sheet_open"] == 0

    apply_verified_action(ctx, "swipe", "verified", {"direction": "up", "zone": "reels_rail"}, executor_ok=True)
    assert ctx["reels_scrolled"] == 1
    assert ctx["ready_for_next_reel"] == 0
    assert 2 <= ctx["comment_likes_this_reel_target"] <= 5
