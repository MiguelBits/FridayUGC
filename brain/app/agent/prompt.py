from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import get_settings
from ..ugc.operator import playbook_text
from .actions import Screen, ScreenState, StepRequest, StepResponse
from .intents import INTENT_SPEC
from .perception import is_reels_viewer, on_comments_sheet, on_reels_surface, resolve_state, screen_state_block

VALID_ACTIONS = frozenset({
    "tap", "scroll", "swipe", "type", "press", "open_app", "wait", "intent", "navigate",
    "post", "comment", "dm", "like", "like_story", "like_comment", "view_story", "follow",
    "unfollow", "save", "done", "fail",
})

COMMENT_LIKES_PLAYBOOK = (
    "\nINSTAGRAM WORKFLOW — reels_comment_likes (intent-first):\n"
    "1. If not reels_viewer → intent enter_reels (or navigate tab=reels).\n"
    "2. On reels_viewer → intent watch_reel (dwell 2–5s), then intent open_comments.\n"
    "3. On comments_sheet → intent engage_comments until per-reel budget met, then intent go_back.\n"
    "4. intent next_reel — repeat until reels_scrolled >= reels_max.\n"
    "Phone resolves intents with vision + device memory — never hardcoded coordinates.\n"
)

AGENT_ROLE = (
    "\nROLE: Cognitive mobile operator. Plan ONE high-level step per turn — prefer intents over raw taps.\n"
    "Target app: INSTAGRAM (com.instagram.android) for @itslorenamor UGC.\n"
    "You receive STRUCTURED SCREEN_STATE from the phone classifier — trust it over single words in the tree.\n"
    "When needs_vision=true or a screenshot is attached, USE THE IMAGE — icon-only UIs are blind in elements.\n"
    "Behave like a human: vary dwell times, skip boring reels, do not repeat failed actions.\n"
)

PERCEPTION_RULES = (
    "\nPERCEPTION RULES:\n"
    "- screen_type is authoritative for where you are (home_feed ≠ reels_viewer).\n"
    "- Bottom-nav label 'Reels' visible on home_feed does NOT mean reels_viewer.\n"
    "- confidence < 0.55 or screen_type=unknown → prefer wait+needs_screenshot or navigate, not swipe.\n"
    "- LAST_ACTION verified=failed/unverified → change strategy; do not repeat same tap.\n"
)

NEGATIVES = (
    "\nNEVER (violations waste steps):\n"
    "- NEVER swipe LEFT or RIGHT during reels work — use intent enter_reels or navigate tab=reels; then intent next_reel only.\n"
    "- NEVER tap story circles at the TOP of home feed — that opens Stories, not Reels.\n"
    "- NEVER use view_story or like_story when goal is reels / comment-likes on Reels.\n"
    "- NEVER open Chrome/browser/instagram.com — only open_app com.instagram.android.\n"
    "- NEVER post new comments when goal is comment LIKES (use like_comment only).\n"
    "- NEVER return done before SESSION_BUDGET phase goals are met.\n"
    "- NEVER tap without x,y or target_id from SCREEN ELEMENTS / screenshot.\n"
    "- NEVER assume executor ok=true means success — check LAST_ACTION verified field.\n"
)

INSTAGRAM_NAV = (
    "\nINSTAGRAM NAVIGATION (prefer intents — phone binds motor at execution time):\n"
    "- STORIES: horizontal avatar circles at TOP of home feed → opens story_viewer (full-screen stories).\n"
    "- REELS: intent enter_reels — phone uses bottom nav, deep link, device memory, then ONE controlled swipe LEFT if needed. NEVER swipe RIGHT.\n"
    "- REELS alt: {\"action\":\"navigate\",\"params\":{\"tab\":\"reels\"}} — never tap top story tray.\n"
    "- If screen_type=story_viewer: intent go_back, then intent enter_reels.\n"
)

UI_UNDERSTANDING = (
    "\nEXECUTION: Phone runs your JSON blindly. Coordinates must come from element center= or screenshot.\n"
    "SCREEN ELEMENTS list: id, role, text, bounds, center=x,y. Icon buttons often have empty text — use vision.\n"
)

JSON_EXAMPLE = (
    '{"action":"intent","params":{"name":"next_reel"},"say":"Next reel.","reason":"finished watching",'
    '"done":false,"needs_screenshot":false,"approval_required":false}'
)

ACTION_SPEC = (
    "Valid actions: intent (preferred), tap, scroll, swipe, type, press, open_app, wait, navigate, "
    "like, like_story, like_comment, view_story, save, follow, unfollow, post, comment, dm, done, fail. "
    "intent params: {\"name\":\"<intent>\", ...}. like_comment = heart on a comment row."
)

INSTAGRAM_PACKAGE = "com.instagram.android"


def goal_wants_instagram(goal: str) -> bool:
    g = goal.lower()
    return any(
        k in g
        for k in ("instagram", "insta", " ig", "scroll", "reel", "feed", "like", "story", "inbox")
    )


def goal_wants_scroll(goal: str) -> bool:
    g = goal.lower()
    if goal_wants_comment_likes(goal):
        return False
    return any(k in g for k in ("scroll", "feed", "reel", "browse", "watch"))


def goal_wants_comment_likes(goal: str) -> bool:
    g = goal.lower()
    return ("like" in g and "comment" in g and ("reel" in g or "reels" in g)) or "reels_comment_likes" in g


def on_instagram(screen_app: str) -> bool:
    return "instagram" in (screen_app or "").lower()


def on_reels_view(screen: Screen, screen_state: ScreenState | None = None) -> bool:
    state = resolve_state(StepRequest(session_id="", goal="", screen=screen, screen_state=screen_state))
    return is_reels_viewer(state)


def fallback_step_data(req: StepRequest) -> dict:
    """Safe action when the model returns garbage or unparseable JSON."""
    state = resolve_state(req)
    if goal_wants_instagram(req.goal) and not on_instagram(req.screen.app):
        return {
            "action": "open_app",
            "params": {"package": INSTAGRAM_PACKAGE},
            "say": "Opening Instagram.",
            "reason": "Fallback — model output was not valid JSON.",
            "done": False,
            "needs_screenshot": False,
            "approval_required": False,
        }
    if goal_wants_comment_likes(req.goal) and on_instagram(req.screen.app) and not on_reels_surface(
        state, req.session_context or {}, req.screen
    ):
        return {
            "action": "navigate",
            "params": {"tab": "reels"},
            "say": "Opening Reels tab.",
            "reason": f"Fallback — screen_type={state.screen_type}, need reels_viewer.",
            "done": False,
            "needs_screenshot": state.needs_vision,
            "approval_required": False,
        }
    kick = None
    if goal_wants_comment_likes(req.goal):
        from .playbook import comment_likes_kickstart

        kick = comment_likes_kickstart(req, state)
    if kick:
        return kick.model_dump()
    if state.needs_vision and not (req.screen.screenshot_b64 or "").strip():
        return {
            "action": "wait",
            "params": {"ms": 300},
            "say": "Need screenshot.",
            "reason": f"Fallback — low confidence ({state.confidence:.2f}) or sparse tree.",
            "done": False,
            "needs_screenshot": True,
            "approval_required": False,
        }
    return {
        "action": "intent",
        "params": {"name": "next_reel"},
        "say": "Next reel.",
        "reason": "Fallback — model output was not valid JSON.",
        "done": False,
        "needs_screenshot": False,
        "approval_required": False,
    }


_PLAYBOOK = Path(__file__).resolve().parent / "ugc_operator_prompt.md"


def elements_to_text(screen: Screen) -> str:
    if not screen.elements:
        hint = "(no accessible elements"
        if screen.screenshot_b64:
            hint += " — use attached screenshot to find buttons"
        return hint + ")"
    lines = []
    for e in screen.elements:
        flags = []
        if e.clickable:
            flags.append("clickable")
        if e.scrollable:
            flags.append("scrollable")
        if e.editable:
            flags.append("editable")
        flag = f" [{','.join(flags)}]" if flags else ""
        pos = f" @{e.x},{e.y} {e.w}x{e.h}" if e.w > 0 and e.h > 0 else ""
        cx = e.x + e.w // 2 if e.w > 0 else 0
        cy = e.y + e.h // 2 if e.h > 0 else 0
        center = f" center={cx},{cy}" if cx > 0 and cy > 0 else ""
        lines.append(f"  {e.id}: {e.role} {e.text!r}{pos}{center}{flag}")
    if screen.screenshot_b64:
        lines.append("  (screenshot attached — use image + elements together)")
    return "\n".join(lines)


def detect_loop(history: list[str], k: int = 3) -> bool:
    return len(history) >= k and len(set(history[-k:])) == 1


def ctx_int(ctx: dict, key: str, default: int = 0) -> int:
    try:
        return int(ctx.get(key, default))
    except (TypeError, ValueError):
        return default


def budget_exceeded(action: str, ctx: dict) -> tuple[bool, str]:
    phase = str(ctx.get("phase", ""))
    if action == "like_comment":
        per_reel = ctx_int(ctx, "comment_likes_per_reel", 5)
        this_reel = ctx_int(ctx, "comment_likes_this_reel")
        if this_reel >= per_reel:
            return True, f"reel comment likes done ({this_reel}/{per_reel}) — press back"
        if ctx_int(ctx, "comment_likes_used") >= ctx_int(ctx, "comment_likes_max", 50):
            return True, "comment likes session budget hit — done"
    if action == "swipe" and phase == "reels_comment_likes":
        if ctx_int(ctx, "reels_scrolled") >= ctx_int(ctx, "reels_max", 10):
            return True, "10 reels completed — return done"
    checks = {
        "like": ("likes_used", "likes_max", "swipe"),
        "like_story": ("story_likes_used", "story_likes_max", "view_story"),
        "comment": ("comments_used", "comments_max", "navigate"),
        "dm": ("dms_used", "dms_max", "navigate"),
        "follow": ("follows_used", "follows_max", "navigate"),
        "save": ("saves_used", "saves_max", "scroll"),
    }
    if action == "swipe" and phase != "reels_comment_likes" and ctx_int(ctx, "reels_scrolled") >= ctx_int(ctx, "reels_max", 999):
        return True, "reels_scroll budget hit — move to stories or inbox"
    if action not in checks:
        return False, ""
    used_k, max_k, _fallback = checks[action]
    if ctx_int(ctx, used_k) >= ctx_int(ctx, max_k, 999):
        return True, f"{action} budget hit ({ctx.get(used_k)}/{ctx.get(max_k)})"
    return False, ""


def budget_fallback(action: str, reason: str) -> StepResponse:
    fallback_action = "navigate"
    params: dict = {"tab": "inbox"}
    if "reels" in reason:
        params = {"tab": "home"}
    elif "like" in action:
        fallback_action = "press" if "comment likes done" in reason.lower() else "swipe"
        params = {"key": "back"} if fallback_action == "press" else {"direction": "up"}
    return StepResponse(
        action=fallback_action,  # type: ignore[arg-type]
        params=params,
        say="Budget reached — switching phase.",
        reason=reason,
        done=False,
        needs_screenshot=False,
        approval_required=False,
    )


def build_step_user_prompt(req: StepRequest) -> str:
    ctx = req.session_context or {}
    loop_hint = ""
    if detect_loop(req.history):
        loop_hint = (
            "\nNOTE: Actions repeated — stuck? press back, navigate elsewhere, or dismiss dialog.\n"
        )

    mode_hint = ""
    if req.mode == "read_only":
        mode_hint = (
            "\nMODE: read_only — ONLY navigate, scroll, swipe, view_story, wait, open_app, done. "
            "NO likes, comments, DMs, follows, saves, posts, or typing.\n"
        )

    comment_likes_line = ""
    if ctx_int(ctx, "comment_likes_max") or goal_wants_comment_likes(req.goal) or ctx.get("phase") == "reels_comment_likes":
        comment_likes_line = (
            f"comment_likes {ctx_int(ctx,'comment_likes_used')}/{ctx_int(ctx,'comment_likes_max',50)} "
            f"(this reel {ctx_int(ctx,'comment_likes_this_reel')}/{ctx_int(ctx,'comment_likes_per_reel',5)}), "
        )

    budget_line = ""
    if ctx:
        budget_line = (
            f"\nSESSION_BUDGET: {comment_likes_line}"
            f"likes {ctx_int(ctx,'likes_used')}/{ctx_int(ctx,'likes_max',25)}, "
            f"story_likes {ctx_int(ctx,'story_likes_used')}/{ctx_int(ctx,'story_likes_max',12)}, "
            f"reels {ctx_int(ctx,'reels_scrolled')}/{ctx_int(ctx,'reels_max',35)}, "
            f"comments {ctx_int(ctx,'comments_used')}/{ctx_int(ctx,'comments_max',8)}, "
            f"dms {ctx_int(ctx,'dms_used')}/{ctx_int(ctx,'dms_max',10)}, "
            f"phase={ctx.get('phase','reels')}\n"
        )

    workflow_hint = ""
    if goal_wants_comment_likes(req.goal) or ctx.get("phase") == "reels_comment_likes":
        workflow_hint = COMMENT_LIKES_PLAYBOOK

    nav_hint = INSTAGRAM_NAV if goal_wants_instagram(req.goal) or on_instagram(req.screen.app) else ""

    last_line = ""
    if req.last_result:
        lr = req.last_result
        verify_bit = ""
        if lr.verified:
            verify_bit = f" verified={lr.verified} change={lr.change_score:.2f}"
        last_line = (
            f"\nLAST_ACTION: {lr.action} ok={lr.ok}{verify_bit}"
            + (f" error={lr.error!r}" if lr.error else "")
            + "\n"
        )
        if lr.verified in {"failed", "unverified"}:
            last_line += "LAST_STEP_DID_NOT_VERIFY — use screenshot + different target.\n"

    memory_hint = ""
    if req.device_id:
        from ..learning.service import LearningService

        memory_hint = LearningService().memory_hints(req.device_id)

    operator = playbook_text() if _PLAYBOOK.is_file() else ""
    state = resolve_state(req)
    state_line = screen_state_block(state)

    return (
        "RETURN_ACTION_JSON\n"
        f"{AGENT_ROLE}"
        f"{PERCEPTION_RULES}"
        f"{NEGATIVES}"
        f"{nav_hint}"
        f"{INTENT_SPEC}"
        "Return ONE action as valid JSON only (double-quoted keys, no markdown, no prose). "
        "Fields: action, params, say, reason, done, needs_screenshot, approval_required.\n"
        f"INSTAGRAM PACKAGE: {INSTAGRAM_PACKAGE!r} — never browser/URL.\n"
        "On reels_viewer: swipe up for next reel. On home_feed: navigate to target tab first.\n"
        f"EXAMPLE JSON:\n{JSON_EXAMPLE}\n"
        f"{ACTION_SPEC}\n\n"
        f"{UI_UNDERSTANDING}"
        f"{memory_hint}"
        f"{operator[:800]}\n"
        f"{mode_hint}{workflow_hint}{budget_line}{last_line}"
        f"{state_line}"
        f"FOREGROUND APP: {req.screen.app or 'unknown'}\n"
        f"GOAL: {req.goal}\n"
        f"STEP: {req.step}\n"
        f"ACTIVITY: {req.screen.activity or state.activity_class or 'unknown'}\n"
        f"RECENT ACTIONS: {req.history[-8:]}\n"
        f"SCREEN ELEMENTS:\n{elements_to_text(req.screen)}"
        f"{loop_hint}"
    )


def _parse_inline_action(action: str) -> tuple[str, dict]:
    """Fix model output like swipe{"direction": "up"} or swipe{direction: up}."""
    raw = (action or "wait").strip()
    if "{" not in raw:
        name = raw.split()[0].lower()
        return (name if name in VALID_ACTIONS else "wait"), {}

    name, rest = raw.split("{", 1)
    name = name.strip().lower()
    frag = "{" + rest.rstrip()
    if not frag.endswith("}"):
        frag += "}"

    params: dict = {}
    try:
        parsed = json.loads(frag)
        if isinstance(parsed, dict):
            params = parsed
    except json.JSONDecodeError:
        direction = re.search(r"direction\s*:\s*['\"]?(\w+)['\"]?", frag, re.I)
        if direction:
            params["direction"] = direction.group(1).lower()
        package = re.search(r"package\s*:\s*['\"]?([^'\"}\s]+)['\"]?", frag, re.I)
        if package:
            params["package"] = package.group(1)
        tab = re.search(r"tab\s*:\s*['\"]?(\w+)['\"]?", frag, re.I)
        if tab:
            params["tab"] = tab.group(1).lower()
        target = re.search(r"target_id\s*:\s*(\d+)", frag, re.I)
        if target:
            params["target_id"] = int(target.group(1))

    if name not in VALID_ACTIONS:
        for candidate in VALID_ACTIONS:
            if raw.lower().startswith(candidate):
                name = candidate
                break
        else:
            name = "wait"

    return name, params


def normalize_step_data(data: dict) -> dict:
    if not data:
        return data
    out = dict(data)
    action = out.get("action", "wait")
    if isinstance(action, str) and ("{" in action or action.split()[0].lower() not in VALID_ACTIONS):
        name, inline_params = _parse_inline_action(action)
        out["action"] = name
        if inline_params and not out.get("params"):
            out["params"] = inline_params
    elif isinstance(action, str):
        out["action"] = action.strip().split()[0].lower()
    if out.get("action") not in VALID_ACTIONS:
        out["action"] = "wait"
    if not isinstance(out.get("params"), dict):
        out["params"] = {}
    return out


def parse_step_json(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        return {}
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return normalize_step_data(data)
        except json.JSONDecodeError:
            continue
    # Whole response might be action{params} without outer braces.
    if "{" in text:
        name, params = _parse_inline_action(text.split()[0] if text.split() else text)
        if name in VALID_ACTIONS:
            return normalize_step_data({"action": text, "params": params})
    return {}


def response_from_json(data: dict) -> StepResponse:
    data = normalize_step_data(data)
    return StepResponse(
        action=data.get("action", "wait"),  # type: ignore[arg-type]
        params=data.get("params", {}) or {},
        say=data.get("say"),
        reason=data.get("reason", ""),
        done=bool(data.get("done", False)),
        needs_screenshot=bool(data.get("needs_screenshot", False)),
        approval_required=bool(data.get("approval_required", False)),
    )


def apply_guards(req: StepRequest, resp: StepResponse) -> StepResponse:
    settings = get_settings()
    if resp.action in settings.approval_action_set:
        resp.approval_required = True

    ctx = req.session_context or {}
    state = resolve_state(req)

    if req.mode == "read_only" and resp.action in settings.read_only_blocked_set:
        return StepResponse(
            action="swipe",
            params={"direction": "up"},
            say="Read-only — scrolling reels.",
            reason=f"Blocked {resp.action} in read_only",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )

    if goal_wants_comment_likes(req.goal) and on_comments_sheet(state, ctx):
        per_reel = ctx_int(ctx, "comment_likes_per_reel", 5)
        if ctx_int(ctx, "comment_likes_this_reel") < per_reel:
            if resp.action in {"scroll", "swipe"}:
                from .playbook import comment_likes_like_hearts

                kick = comment_likes_like_hearts(req, state)
                if kick:
                    return kick
            if resp.action == "tap" and "comment" not in (resp.reason or "").lower():
                from .playbook import comment_likes_like_hearts

                kick = comment_likes_like_hearts(req, state)
                if kick:
                    return kick

    if goal_wants_comment_likes(req.goal) and resp.action in {"swipe", "scroll"}:
        direction = str(resp.params.get("direction", "")).lower()
        if direction == "right":
            return StepResponse(
                action="intent",
                params={"name": "enter_reels"},
                say="Blocked swipe RIGHT — opening Reels.",
                reason="Swipe RIGHT opens Stories — blocked; use enter_reels or swipe LEFT only",
                done=False,
                needs_screenshot=False,
                approval_required=False,
            )

    if goal_wants_comment_likes(req.goal) and resp.action in {"swipe", "scroll"}:
        direction = str(resp.params.get("direction", "")).lower()
        if direction in {"left", "right"}:
            ctx = req.session_context or {}
            if not on_reels_surface(state, ctx, req.screen):
                return StepResponse(
                    action="intent",
                    params={"name": "enter_reels"},
                    say="Opening Reels.",
                    reason=f"Blocked horizontal {direction} before reels_viewer — intent enter_reels",
                    done=False,
                    needs_screenshot=False,
                    approval_required=False,
                )
            return StepResponse(
                action="wait",
                params={"ms": 400},
                say="Stay on Reels — no horizontal swipes.",
                reason=f"Blocked {resp.action} {direction} during reels_comment_likes",
                done=False,
                needs_screenshot=False,
                approval_required=False,
            )

    # Before reels_tab_opened is confirmed, block LLM from emitting raw tap x,y — those
    # coords are hallucinated on icon-only Instagram bottom nav. Force intent enter_reels.
    if (
        goal_wants_comment_likes(req.goal)
        and not on_reels_surface(state, req.session_context or {}, req.screen)
        and resp.action == "tap"
        and ("x" in resp.params or "y" in resp.params)
    ):
        return StepResponse(
            action="intent",
            params={"name": "enter_reels"},
            say="Opening Reels first.",
            reason="Blocked raw tap during enter-Reels phase — LLM cannot hallucinate coords",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )

    if goal_wants_comment_likes(req.goal) and resp.action == "intent":
        name = str(resp.params.get("name", "")).lower()
        on_reels = on_reels_surface(state, ctx, req.screen)
        if name == "enter_reels" and on_reels:
            return StepResponse(
                action="wait",
                params={"ms": 400},
                say="Already on Reels.",
                reason="enter_reels skipped — already on reels surface",
                done=False,
                needs_screenshot=False,
                approval_required=False,
            )
        if name in {"open_comments", "engage_comments", "next_reel", "watch_reel"} and not on_reels:
            return StepResponse(
                action="navigate",
                params={"tab": "reels"},
                say="Opening Reels first.",
                reason=f"Blocked intent {name} — need reels_viewer, have {state.screen_type}",
                done=False,
                needs_screenshot=state.needs_vision,
                approval_required=False,
            )

    if goal_wants_comment_likes(req.goal) and resp.action == "navigate":
        tab = str(resp.params.get("tab", "")).lower()
        if tab == "reels" and on_reels_surface(state, ctx, req.screen):
            return StepResponse(
                action="wait",
                params={"ms": 400},
                say="Already on Reels.",
                reason="reels_tab_opened — skip repeat navigate",
                done=False,
                needs_screenshot=False,
                approval_required=False,
            )

    if goal_wants_comment_likes(req.goal) and resp.action in {"view_story", "like_story"}:
        return StepResponse(
            action="navigate",
            params={"tab": "reels"},
            say="Stories blocked — opening Reels.",
            reason=f"Goal is Reels comment-likes, not stories (blocked {resp.action})",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )

    if goal_wants_comment_likes(req.goal) and state.screen_type == "story_viewer":
        if resp.action != "press":
            return StepResponse(
                action="press",
                params={"key": "back"},
                say="Leaving Stories.",
                reason="story_viewer is wrong surface for comment-likes — back then navigate reels",
                done=False,
                needs_screenshot=False,
                approval_required=False,
            )

    if goal_wants_comment_likes(req.goal) and resp.action in {"swipe", "scroll"}:
        if (
            ctx_int(ctx, "reels_scrolled") == 0
            and ctx_int(ctx, "comment_likes_this_reel") == 0
            and not on_reels_surface(state, ctx, req.screen)
        ):
            return StepResponse(
                action="navigate",
                params={"tab": "reels"},
                say="Opening Reels first.",
                reason=f"Comment-likes needs reels_viewer, have {state.screen_type}",
                done=False,
                needs_screenshot=state.needs_vision,
                approval_required=False,
            )

    if state.screen_type == "home_feed" and resp.action in {"swipe", "scroll"} and goal_wants_comment_likes(req.goal):
        if on_reels_surface(state, ctx, req.screen) and resp.action == "swipe":
            direction = str(resp.params.get("direction", "")).lower()
            if direction == "up":
                return resp
        if not on_reels_surface(state, ctx, req.screen):
            return StepResponse(
                action="navigate",
                params={"tab": "reels"},
                say="Leaving home feed for Reels.",
                reason="Do not swipe home feed during comment-likes goal",
                done=False,
                needs_screenshot=False,
                approval_required=False,
            )

    if (
        state.confidence < 0.45
        and resp.action in {"tap", "like_comment"}
        and not (req.screen.screenshot_b64 or "").strip()
        and goal_wants_comment_likes(req.goal)
    ):
        return StepResponse(
            action="wait",
            params={"ms": 300},
            say="Low confidence — need screenshot.",
            reason=f"screen_type={state.screen_type} confidence={state.confidence:.2f}",
            done=False,
            needs_screenshot=True,
            approval_required=False,
        )

    # Posting comments is blocked unless goal asks; like_comment is for hearts on existing comments.
    if resp.action == "comment" and goal_wants_comment_likes(req.goal):
        return StepResponse(
            action="like_comment",
            params=resp.params,
            say="Liking comment, not posting.",
            reason="Goal wants comment likes, not new comments",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )

    if resp.action == "like" and goal_wants_comment_likes(req.goal):
        return StepResponse(
            action="like_comment",
            params=resp.params,
            say="Liking comment heart.",
            reason="Remapped like → like_comment for comment-likes goal",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )

    # No comments unless the goal explicitly asks for them.
    if resp.action == "comment" and "comment" not in req.goal.lower():
        return StepResponse(
            action="swipe",
            params={"direction": "up"},
            say="Skipping comment.",
            reason="Comments disabled for this goal",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )

    # Last tap failed — don't retry tap (target_id is stale after long inference).
    if req.last_result and req.last_result.action == "tap" and req.last_result.ok is False:
        if goal_wants_comment_likes(req.goal) and on_reels_surface(state, ctx, req.screen):
            from .playbook import comment_likes_kickstart

            kick = comment_likes_kickstart(req, state)
            if kick:
                return kick
        if goal_wants_comment_likes(req.goal):
            return StepResponse(
                action="navigate",
                params={"tab": "reels"},
                say="Tap missed — trying Reels tab.",
                reason=f"Last tap failed: {req.last_result.error}",
                done=False,
                needs_screenshot=False,
                approval_required=False,
            )
        return StepResponse(
            action="swipe",
            params={"direction": "up"},
            say="Tap missed — scrolling instead.",
            reason=f"Last tap failed: {req.last_result.error}",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )

    # Scroll goals on Instagram: swipe beats tap (target_ids go stale during inference).
    if resp.action == "tap" and on_instagram(req.screen.app) and goal_wants_scroll(req.goal):
        return StepResponse(
            action="swipe",
            params={"direction": "up"},
            say="Scrolling feed.",
            reason="Remapped tap → swipe for scroll goal on Instagram",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )

    if detect_loop(req.history) and resp.action == "tap":
        return StepResponse(
            action="swipe",
            params={"direction": "up"},
            say="Unstuck — scrolling.",
            reason="Repeated tap — switching to swipe",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )

    # Force correct Instagram package — model sometimes returns google/chrome/URLs.
    if resp.action == "open_app":
        pkg = str(resp.params.get("package", ""))
        if on_instagram(req.screen.app):
            if goal_wants_comment_likes(req.goal):
                return StepResponse(
                    action="navigate",
                    params={"tab": "reels"},
                    say="On Instagram — opening Reels.",
                    reason=f"Ignored open_app while on {req.screen.app!r}",
                    done=False,
                    needs_screenshot=False,
                    approval_required=False,
                )
            return StepResponse(
                action="swipe",
                params={"direction": "up"},
                say="Already on Instagram — scrolling.",
                reason=f"Ignored open_app while on {req.screen.app!r}",
                done=False,
                needs_screenshot=False,
                approval_required=False,
            )
        bad = (
            not pkg
            or "http" in pkg.lower()
            or "instagram.com" in pkg.lower()
            or "google" in pkg.lower()
            or "chrome" in pkg.lower()
            or "browser" in pkg.lower()
            or pkg != INSTAGRAM_PACKAGE
        )
        if bad and goal_wants_instagram(req.goal):
            return StepResponse(
                action="open_app",
                params={"package": INSTAGRAM_PACKAGE},
                say="Opening Instagram.",
                reason=f"Corrected bad open_app package {pkg!r}",
                done=False,
                needs_screenshot=False,
                approval_required=False,
            )

    ctx = req.session_context or {}
    exceeded, breason = budget_exceeded(resp.action, ctx)
    if exceeded and req.mode == "full":
        return budget_fallback(resp.action, breason)

    if (resp.done or resp.action == "done") and goal_wants_comment_likes(req.goal):
        reels_done = ctx_int(ctx, "reels_scrolled") >= ctx_int(ctx, "reels_max", 10)
        likes_done = ctx_int(ctx, "comment_likes_used") >= ctx_int(ctx, "comment_likes_max", 50)
        if not (reels_done or likes_done):
            return StepResponse(
                action="navigate",
                params={"tab": "reels"},
                say="Continuing comment-likes routine.",
                reason="Ignored premature done — reels/comment-like budget not met",
                done=False,
                needs_screenshot=False,
                approval_required=False,
            )

    # Model sometimes returns done before Instagram is open or any action ran.
    if (resp.done or resp.action == "done") and req.step < 5 and goal_wants_instagram(req.goal) and not on_instagram(req.screen.app):
        return StepResponse(
            action="open_app",
            params={"package": INSTAGRAM_PACKAGE},
            say="Opening Instagram.",
            reason="Ignored premature done — Instagram not in foreground yet.",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )

    return resp
