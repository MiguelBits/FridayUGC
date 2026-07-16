from __future__ import annotations

import json

from .base import ChatMessage, LLMClient


class MockClient(LLMClient):
    """Deterministic, GPU-free client for local dev, CI, and offline testing."""

    @staticmethod
    def _instagram_foreground(prompt: str) -> bool:
        if "FOREGROUND APP: com.instagram.android" in prompt:
            return True
        if "app=com.instagram.android" in prompt:
            return True
        if any(
            s in prompt
            for s in (
                "screen_type=home_feed",
                "screen_type=reels_viewer",
                "screen_type=comments_sheet",
                "screen_type=inbox",
                "screen_type=search",
                "screen_type=profile",
            )
        ):
            return True
        return False

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        last = messages[-1].content if messages else ""

        if "GROUND_TARGET_JSON" in last:
            w, h = 1080, 2400
            if "SCREEN_SIZE:" in last:
                size = last.split("SCREEN_SIZE:")[-1].split("\n")[0].strip()
                if "x" in size:
                    parts = size.split("x")
                    try:
                        w, h = int(parts[0]), int(parts[1])
                    except (ValueError, IndexError):
                        pass
            anchor = "comments_icon"
            if "ANCHOR:" in last:
                anchor = last.split("ANCHOR:")[-1].split("\n")[0].strip()
            row = 0
            if "row index" in last:
                import re as _re
                m = _re.search(r"row index (\d+)", last)
                if m:
                    row = int(m.group(1))
            presets = {
                "comments_icon": (int(w * 0.93), int(h * 0.52)),
                "comment_heart": (int(w * 0.86), int(h * (0.55 + 0.07 * row))),
                "nav_reels": (int(w * 0.50), int(h * (0.955 if h / max(w, 1) >= 2.1 else 0.965))),
            }
            x, y = presets.get(anchor, (w // 2, h // 2))
            action = "like_comment" if anchor == "comment_heart" else "tap"
            return json.dumps({
                "action": action,
                "params": {"x": x, "y": y},
                "confidence": 0.8,
                "reason": f"mock ground {anchor}",
            })

        # Agent step: return a valid action JSON.
        if "RETURN_ACTION_JSON" in last:
            goal = ""
            if "GOAL:" in last:
                goal = last.split("GOAL:")[-1].split("\n")[0].strip().lower()
            if "FORCE_LIKE_ACTION" in last:
                action = {
                    "action": "like",
                    "params": {"target_id": 0},
                    "say": "Liking this post.",
                    "reason": "Test trigger for read_only enforcement.",
                    "done": False,
                    "needs_screenshot": False,
                    "approval_required": False,
                }
            elif not self._instagram_foreground(last):
                action = {
                    "action": "open_app",
                    "params": {"package": "com.instagram.android"},
                    "say": "Opening Instagram.",
                    "reason": "Instagram is not in the foreground yet.",
                    "done": False,
                    "needs_screenshot": False,
                    "approval_required": False,
                }
            elif (goal.startswith("post ") or " post " in f" {goal} ") and "like" not in goal:
                action = {
                    "action": "post",
                    "params": {"caption": "Miami fit check."},
                    "say": "Posting reel.",
                    "reason": "Scheduled post from gallery queue.",
                    "done": False,
                    "needs_screenshot": False,
                    "approval_required": True,
                }
            elif "GOAL:" in last and ("reel" in goal or "reels_comment_likes" in goal or "comment like" in goal):
                if "screen_type=reels_viewer" in last and "comment_likes_this_reel" in last:
                    action = {
                        "action": "intent",
                        "params": {"name": "open_comments"},
                        "say": "Opening comments.",
                        "reason": "On reels — open comments via intent.",
                        "done": False,
                        "needs_screenshot": False,
                        "approval_required": False,
                    }
                elif "screen_type=comments_sheet" in last:
                    action = {
                        "action": "intent",
                        "params": {"name": "engage_comments"},
                        "say": "Liking a comment.",
                        "reason": "On comments sheet.",
                        "done": False,
                        "needs_screenshot": False,
                        "approval_required": False,
                    }
                elif "screen_type=home_feed" in last or "for you" in last.lower():
                    action = {
                        "action": "navigate",
                        "params": {"tab": "reels"},
                        "say": "Opening Reels tab.",
                        "reason": "Home feed — navigate to Reels tab first.",
                        "done": False,
                        "needs_screenshot": False,
                        "approval_required": False,
                    }
                else:
                    action = {
                        "action": "navigate",
                        "params": {"tab": "reels"},
                        "say": "Opening Reels tab.",
                        "reason": "Reels work — navigate to Reels tab.",
                        "done": False,
                        "needs_screenshot": False,
                        "approval_required": False,
                    }
            elif goal and ("story" in goal or "stories" in goal):
                action = {
                    "action": "view_story",
                    "params": {"target_id": 0},
                    "say": "Watching a story.",
                    "reason": "Stories phase — view creator stories.",
                    "done": False,
                    "needs_screenshot": False,
                    "approval_required": False,
                }
            elif goal and ("inbox" in goal or "dm" in goal):
                action = {
                    "action": "navigate",
                    "params": {"tab": "inbox"},
                    "say": "Opening inbox.",
                    "reason": "Check DMs selectively per inbox policy.",
                    "done": False,
                    "needs_screenshot": False,
                    "approval_required": False,
                }
            elif goal and ("comment" in goal or "activity" in goal):
                action = {
                    "action": "navigate",
                    "params": {"tab": "activity"},
                    "say": "Opening notifications.",
                    "reason": "Find comments on our posts to reply.",
                    "done": False,
                    "needs_screenshot": False,
                    "approval_required": False,
                }
            elif goal and "like" in goal and "read_only" not in last.lower():
                action = {
                    "action": "like",
                    "params": {"target_id": 0},
                    "say": "Liking niche post.",
                    "reason": "Engagement within session budget.",
                    "done": False,
                    "needs_screenshot": False,
                    "approval_required": False,
                }
            else:
                action = {
                    "action": "scroll",
                    "params": {"direction": "down"},
                    "say": "Scrolling the feed.",
                    "reason": "Instagram is open; scroll to find niche posts.",
                    "done": False,
                    "needs_screenshot": False,
                    "approval_required": False,
                }
            return json.dumps(action)

        # UGC caption
        if "RETURN_CAPTION" in last:
            return "Wrong mirror. Right dress. Dressing room girlies — yes or no 👇"

        # UGC plan
        if "RETURN_PLAN_JSON" in last:
            return json.dumps(
                {
                    "lane": "A",
                    "type": "outfit try-on",
                    "cta": 1,
                    "code": "*A(outfit try-on)1*",
                    "on_screen_text": "WASN'T POSTING THIS",
                    "hook": "Mirror reveal — no dialogue first beat.",
                    "caption": "Wrong mirror. Right dress. Yes or no 👇",
                }
            )

        # Voice reply
        if "RETURN_VOICE" in last:
            return "Done. Liked two posts and left one comment in your voice."

        # Gallery curation (2026 UGC director)
        if "RETURN_CURATE_JSON" in last:
            from datetime import date, timedelta

            d0 = date.today().isoformat()
            d1 = (date.today() + timedelta(days=1)).isoformat()
            return json.dumps(
                {
                    "posting_queue": [
                        {
                            "asset_ids": ["reel_leg_01", "reel_leg_02"],
                            "format": "reel",
                            "lane": "D",
                            "type": "workout exercise",
                            "cta": 1,
                            "code": "*D(workout exercise)1*",
                            "on_screen_text": "MOVE",
                            "caption": "Two leg days back to back. Tell me no.",
                            "hashtags": ["#legday", "#gymgirl", "#miami"],
                            "scheduled_date": d0,
                            "pillar": "gym",
                            "pairing_reason": "Same gym session energy — leg day batch",
                        },
                        {
                            "asset_ids": ["reel_outfit_01", "slide_outfit_02"],
                            "format": "carousel",
                            "lane": "A",
                            "type": "outfit try-on",
                            "cta": 1,
                            "code": "*A(outfit try-on)1*",
                            "on_screen_text": "WRONG MIRROR",
                            "caption": "Wrong mirror. Right fit. Yes or no.",
                            "hashtags": ["#tryonhaul", "#grwm"],
                            "scheduled_date": d1,
                            "pillar": "outfit",
                            "pairing_reason": "Dress + jeans try-on — same dressing room vibe",
                        },
                    ],
                    "carousel_groups": [
                        {
                            "group_id": "outfit_batch_1",
                            "asset_ids": ["reel_outfit_01", "slide_outfit_02"],
                            "theme": "dressing room try-on",
                            "caption": "Wrong mirror. Right fit.",
                            "hashtags": ["#tryonhaul", "#grwm"],
                        }
                    ],
                    "bio_suggestion": "Miami | leg day > everything | meal prep era",
                    "hashtag_bank": [
                        "#legday",
                        "#gymgirl",
                        "#mealprep",
                        "#miami",
                        "#tryonhaul",
                        "#cleaneating",
                    ],
                    "strategy_notes": "Week opens gym-heavy, mid-week outfit carousel, food post Friday.",
                }
            )

        if "RETURN_COMMENT_REPLY" in last:
            return "Bold of you to assume I'd agree."

        if "RETURN_INBOX_DRAFT" in last:
            return "Cute. Still not convinced though."

        if "RETURN_VISION_JSON" in last:
            vibe = "gritty leg day mirror"
            summary = "Gym mirror shot, black athletic wear, squat rack visible, warm overhead lighting."
            pillar = "gym"
            if "outfit" in last:
                vibe = "dressing room try-on smug"
                summary = "Vertical mirror, black ribbed fitted dress, warm bedroom tones, confident pose."
                pillar = "outfit"
            elif "food" in last:
                vibe = "clean eating macro flex"
                summary = "Overhead protein bowl, chicken rice greens, natural kitchen light."
                pillar = "food"
            elif "lifestyle" in last:
                vibe = "miami golden hour soft"
                summary = "Balcony coffee, skyline bokeh, golden hour warm tones."
                pillar = "lifestyle"
            return json.dumps(
                {
                    "vision_summary": summary,
                    "vibe": vibe,
                    "pillar": pillar,
                    "visual_tags": ["ugc", "vertical", "natural light", pillar],
                    "pairing_hints": [f"pairs with other {pillar} content same week"],
                    "suggested_lane": "D" if pillar == "gym" else "A",
                    "suggested_type": "workout exercise" if pillar == "gym" else "outfit try-on",
                    "on_screen_text_hint": "MOVE" if pillar == "gym" else "WRONG MIRROR",
                    "identity_ok": True,
                    "warnings": [],
                }
            )

        return "ok"
