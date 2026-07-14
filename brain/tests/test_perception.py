"""Perception layer: structured screen state + prompt guards."""

from __future__ import annotations

from app.agent.actions import Screen, ScreenElement, ScreenState, StepRequest, StepResponse
from app.agent.perception import classify_screen, is_reels_viewer, resolve_state, screen_state_block
from app.agent.prompt import apply_guards, build_step_user_prompt


def test_screen_state_block_in_prompt():
    req = StepRequest(
        session_id="s1",
        goal="Like comments on reels",
        screen=Screen(app="com.instagram.android", elements=[]),
        screen_state=ScreenState(
            screen_type="home_feed",
            selected_tab="home",
            confidence=0.9,
            signals=["home feed tabs"],
        ),
    )
    prompt = build_step_user_prompt(req)
    assert "SCREEN_STATE" in prompt
    assert "screen_type=home_feed" in prompt
    assert "NEVER" in prompt
    assert "Cognitive mobile operator" in prompt


def test_resolve_state_prefers_phone_classifier():
    state = ScreenState(screen_type="reels_viewer", selected_tab="reels", confidence=0.9)
    req = StepRequest(
        session_id="s1",
        goal="test",
        screen=Screen(app="com.instagram.android", elements=[ScreenElement(id=0, text="For you")]),
        screen_state=state,
    )
    assert is_reels_viewer(resolve_state(req))


def test_guard_blocks_swipe_on_home_feed_comment_likes():
    req = StepRequest(
        session_id="s1",
        goal="Like comments on 10 reels",
        screen=Screen(
            app="com.instagram.android",
            elements=[ScreenElement(id=0, text="For you")],
        ),
        screen_state=ScreenState(screen_type="home_feed", selected_tab="home", confidence=0.9),
        session_context={"phase": "reels_comment_likes", "reels_scrolled": 0},
    )
    guarded = apply_guards(req, StepResponse(action="swipe", params={"direction": "up"}))
    assert guarded.action == "navigate"
    assert guarded.params["tab"] == "reels"


def test_classify_comments_sheet():
    screen = Screen(
        app="com.instagram.android",
        elements=[ScreenElement(id=0, text="Add a comment")],
    )
    state = classify_screen(screen)
    assert state.screen_type == "comments_sheet"


def test_screen_state_block_format():
    block = screen_state_block(
        ScreenState(screen_type="unknown", confidence=0.3, needs_vision=True, signals=["sparse"])
    )
    assert "needs_vision=true" in block
    assert "confidence=0.30" in block
