# Friday Action Protocol (phone ⇄ brain)

The phone stays "dumb": it captures screen state, sends it to the brain, receives **one action**,
executes it, and repeats. The brain (Gemma 4) never touches the phone directly — it only returns
structured JSON that the Android `ActionExecutor` knows how to run.

This contract is the single source of truth. `brain/app/agent/actions.py` and the Android
`ActionExecutor.kt` must both conform to it.

## 1. Phone → Brain: `POST /agent/step`

```json
{
  "session_id": "uuid-per-task",
  "goal": "Open Instagram and scroll the feed for 60s, like AI/gym posts in Lorena's niche",
  "step": 7,
  "screen": {
    "app": "com.instagram.android",
    "activity": "MainActivity",
    "elements": [
      { "id": 0, "role": "button",     "text": "Like",    "scrollable": false, "editable": false },
      { "id": 1, "role": "scrollable", "text": "",         "scrollable": true,  "editable": false },
      { "id": 2, "role": "edittext",   "text": "Comment",  "scrollable": false, "editable": true },
      { "id": 3, "role": "link",       "text": "#gymtok",  "scrollable": false, "editable": false }
    ],
    "screenshot_b64": null
  },
  "last_result": { "action": "scroll", "ok": true, "error": null },
  "history": ["open_app", "wait", "scroll", "scroll"],
  "mode": "read_only",
  "session_context": {
    "likes_used": 3,
    "likes_max": 25,
    "reels_scrolled": 10,
    "reels_max": 35,
    "phase": "reels"
  }
}
```

`mode` is `"read_only"` (default, safe) or `"full"`. In read-only mode the brain and phone block
`post`, `comment`, `dm`, `follow`, `like`, `like_story`, `save`, and `type` — use this for throwaway
accounts and the first week on `@itslorenamor` (scroll + observe + draft captions only).

`session_context` carries per-session engagement budgets. The phone increments counters after each
successful action; the brain enforces caps and switches phases (reels → stories → feed → inbox).

`screenshot_b64` is optional and only sent when the brain requests vision (Reels/Stories/WebViews
where the accessibility tree is weak). Keep it null by default to save bandwidth + latency.

## 2. Brain → Phone: response

```json
{
  "action": "scroll",
  "params": { "direction": "down", "target_id": 1 },
  "say": "Scrolling the feed now.",
  "reason": "Feed is visible; look for niche posts before engaging.",
  "done": false,
  "needs_screenshot": false,
  "approval_required": false
}
```

- `say` — optional text Friday speaks aloud (female TTS). Keep short.
- `approval_required` — if `true`, the phone must get user confirmation before executing
  (used for `post`, `comment`, `dm`, `follow` on the real account by default).
- `needs_screenshot` — if `true`, the phone re-sends the same step with `screenshot_b64` filled.
- `done` — task complete; phone stops the loop.

## 3. Supported actions

| action | params | phone behavior |
|--------|--------|----------------|
| `tap` | `{ "target_id": int }` or `{ "x": int, "y": int }` | click node / gesture tap |
| `scroll` | `{ "direction": "up\|down\|left\|right", "target_id": int? }` | `ACTION_SCROLL_*` or swipe |
| `swipe` | `{ "direction": "...", "distance": "short\|long" }` | `dispatchGesture` swipe |
| `type` | `{ "target_id": int, "text": str }` | set text into editable node |
| `press` | `{ "key": "back\|home\|recents\|enter" }` | global action / key |
| `open_app` | `{ "package": "com.instagram.android" }` | launch intent |
| `navigate` | `{ "tab": "reels\|home\|search\|profile\|inbox\|activity\|create" }` | tap bottom tab |
| `wait` | `{ "ms": int }` | pause (default 800–2500 for human pacing) |
| `intent` | `{ "name": str, "dwell_ms": int?, "direction": str? }` | high-level goal; phone resolves to motor at execution time |
| `post` | `{ "media_path": str, "caption": str }` | run IG post flow (approval-gated) |
| `comment` | `{ "target_id": int, "text": str }` | open comment box + type + send (approval-gated) |
| `dm` | `{ "handle": str, "text": str }` | open DM + send (approval-gated) |
| `like` | `{ "target_id": int }` | tap like on a post |
| `like_story` | `{ "target_id": int }` | tap heart on a story |
| `view_story` | `{ "target_id": int }` | open/watch a story ring |
| `save` | `{ "target_id": int }` | save post to collection |
| `follow` | `{ "target_id": int }` | follow profile (approval-gated) |
| `unfollow` | `{ "target_id": int }` | unfollow profile (approval-gated) |
| `done` | `{ "summary": str }` | end task, report result |
| `fail` | `{ "reason": str }` | abort, report reason |

## 4. UGC operator routine (session planner)

`POST /ugc/routine` returns a multi-phase goal + initial `session_context` budgets for a full operator
session (reels scroll, story likes, feed engagement, selective inbox, comment replies):

```json
{
  "routine": "full_session",
  "duration_minutes": 25,
  "mode": "full",
  "notes": null
}
```

Response includes `goal`, `session_context` (budget caps), and `checklist`. The Android app calls this
then runs the standard `/agent/step` loop with `session_context` on every step.

## 5. UGC content endpoints (not part of the step loop)

These are called when Friday needs to *create* content, not drive the UI:

- `POST /ugc/plan`    → returns a content plan (lane/type/CTA + hook + on-screen text) for a ref.
- `POST /ugc/caption` → returns an Instagram caption in Lorena's voice for a given reel/post.
- `POST /ugc/prompt`  → returns a Seedance/Marketing-Studio generation prompt (UGC block/timed beat).
- `POST /voice/reply` → returns a short spoken reply for Friday's TTS.

See `brain/app/ugc/schemas.py` for exact request/response shapes.

## 6. Vision grounding (Gemma 3, local)

`POST /agent/ground` — phone sends screenshot + anchor (+ optional `som_marks` from Set-of-Marks overlay); brain returns tap coordinates or resolves `mark_id` to x,y.
Used when accessibility tree and device memory cannot bind icon-only Instagram UI.
No OpenAI key required — uses `FRIDAY_VISION_MODEL` (default `google/gemma-3-12b-it`) on vLLM.

GroundRequest fields: `som_marks[]` with `{mark_id, x, y, text, element_id}`, `use_som` (default true when marks present).
