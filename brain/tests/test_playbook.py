"""Playbook kickstart after Reels preflight."""

from __future__ import annotations

from app.agent.actions import Screen, ScreenElement, ScreenState, StepRequest
from app.agent.perception import on_reels_surface, resolve_state
from app.agent.playbook import comment_likes_kickstart


def test_on_reels_surface_rejects_home_feed_with_tabs_even_if_tab_opened():
    state = ScreenState(screen_type="home_feed", confidence=0.9)
    screen = Screen(
        app="com.instagram.android",
        elements=[ScreenElement(id=0, text="For you")],
    )
    assert on_reels_surface(state, {"reels_tab_opened": 1}, screen) is False


def test_on_reels_surface_accepts_reels_viewer():
    state = ScreenState(screen_type="reels_viewer", confidence=0.82)
    assert on_reels_surface(state, {"reels_tab_opened": 0}) is True
    assert on_reels_surface(state, {"reels_tab_opened": 1}) is True


def test_resolve_state_keeps_home_feed_when_tabs_visible():
    req = StepRequest(
        session_id="s1",
        goal="Like comments on 10 reels",
        screen=Screen(
            app="com.instagram.android",
            elements=[ScreenElement(id=0, text="For you")],
        ),
        screen_state=ScreenState(screen_type="home_feed", confidence=0.9),
        session_context={"reels_tab_opened": 1},
    )
    state = resolve_state(req)
    assert state.screen_type == "home_feed"


def test_like_hearts_on_comments_sheet():
    from app.agent.perception import resolve_state

    screen = Screen(
        app="com.instagram.android",
        elements=[
            ScreenElement(id=0, text="user1", clickable=False, y=400, h=40, w=800),
            ScreenElement(id=1, text="", clickable=True, x=950, y=410, w=48, h=48),
            ScreenElement(id=2, text="", clickable=True, x=955, y=520, w=44, h=44),
        ],
    )
    req = StepRequest(
        session_id="s1",
        goal="Like comments on 10 reels",
        screen=screen,
        screen_state=ScreenState(screen_type="unknown", confidence=0.5),
        session_context={
            "reels_tab_opened": 1,
            "comments_sheet_open": 1,
            "comment_likes_this_reel": 0,
            "comment_likes_per_reel": 5,
        },
    )
    from app.agent.playbook import comment_likes_like_hearts

    kick = comment_likes_like_hearts(req, resolve_state(req))
    assert kick is not None
    assert kick.action == "like_comment"
    assert "target_id" in kick.params


def test_kickstart_skipped_on_home_feed():
    req = StepRequest(
        session_id="s1",
        goal="Like comments on 10 reels",
        screen=Screen(
            app="com.instagram.android",
            elements=[ScreenElement(id=0, text="For you", w=1080, h=2400)],
        ),
        screen_state=ScreenState(screen_type="home_feed", confidence=0.9),
        session_context={"reels_tab_opened": 1, "comment_likes_this_reel": 0},
    )
    kick = comment_likes_kickstart(req, resolve_state(req))
    assert kick is None
