"""Protocol parity between Python brain and Android Kotlin models."""

from __future__ import annotations

from app.agent.actions import ScreenElement, StepRequest, StepResponse


def test_step_request_fields():
    req = StepRequest(
        session_id="s1",
        goal="Scroll reels",
        step=2,
        screen={"app": "com.instagram.android", "elements": []},
        session_context={"phase": "reels"},
        device_id="phone-1",
        screen_fingerprint="abc123",
    )
    dumped = req.model_dump()
    assert dumped["session_id"] == "s1"
    assert dumped["device_id"] == "phone-1"
    assert dumped["screen_fingerprint"] == "abc123"
    assert "screen_state" in dumped
    assert dumped["session_context"]["phase"] == "reels"
    assert "screen" in dumped


def test_screen_element_bounds():
    el = ScreenElement(id=1, text="Comment", x=100, y=200, w=40, h=40, clickable=True)
    assert el.x == 100
    assert el.w == 40


def test_step_response_needs_screenshot():
    resp = StepResponse(action="tap", params={"x": 10, "y": 20}, needs_screenshot=True)
    data = resp.model_dump()
    assert data["needs_screenshot"] is True
    assert data["action"] == "tap"


VALID_ACTIONS = {
    "tap", "scroll", "swipe", "type", "press", "open_app", "wait", "navigate",
    "post", "comment", "dm", "like", "like_story", "like_comment", "view_story",
    "follow", "unfollow", "save", "done", "fail",
}


def test_action_names_match_android_protocol_doc():
    from app.agent.actions import ActionName
    import typing

    names = set(typing.get_args(ActionName))
    assert names == VALID_ACTIONS
