"""Guards: comment-likes must navigate to Reels before swiping."""

from __future__ import annotations

from app.agent.actions import Screen, ScreenElement, StepRequest, StepResponse
from app.agent.perception import is_reels_viewer
from app.agent.prompt import apply_guards, fallback_step_data


def test_on_reels_view_rejects_home_feed_tabs():
    from app.agent.prompt import on_reels_view

    screen = Screen(
        app="com.instagram.android",
        elements=[
            ScreenElement(id=0, text="For you", clickable=True),
            ScreenElement(id=1, text="Reels", clickable=True, y=1800, h=48),
        ],
    )
    assert on_reels_view(screen) is False


def test_on_reels_view_accepts_phone_state():
    from app.agent.prompt import on_reels_view
    from app.agent.actions import ScreenState

    screen = Screen(app="com.instagram.android", elements=[])
    state = ScreenState(screen_type="reels_viewer", confidence=0.9)
    assert on_reels_view(screen, state) is True


def test_guard_swipe_becomes_navigate_on_home_feed():
    from app.agent.actions import ScreenState

    req = StepRequest(
        session_id="s1",
        goal="Like comments on 10 reels",
        step=0,
        screen=Screen(
            app="com.instagram.android",
            elements=[ScreenElement(id=0, text="For you"), ScreenElement(id=1, text="Reels")],
        ),
        screen_state=ScreenState(screen_type="home_feed", selected_tab="home", confidence=0.9),
        session_context={"phase": "reels_comment_likes", "reels_scrolled": 0, "comment_likes_this_reel": 0},
    )
    raw = StepResponse(action="swipe", params={"direction": "up"}, reason="scroll")
    guarded = apply_guards(req, raw)
    assert guarded.action == "navigate"
    assert guarded.params["tab"] == "reels"


def test_fallback_navigates_before_swipe():
    req = StepRequest(
        session_id="s1",
        goal="Open Instagram Reels tab. Like comments.",
        step=1,
        screen=Screen(app="com.instagram.android", elements=[ScreenElement(id=0, text="Home")]),
        session_context={"phase": "reels_comment_likes"},
    )
    data = fallback_step_data(req)
    assert data["action"] == "navigate"
    assert data["params"]["tab"] == "reels"
