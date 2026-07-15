# Cognitive Agent Architecture

FridayUGC uses a **two-level cognition model**: the brain plans *intent*, the phone executes *motor*.

## Layers

```
┌─────────────────────────────────────────────────────────┐
│  Brain (Gemma) — cognition                              │
│  • Persona + session budgets                            │
│  • Intent planning (enter_reels, watch_reel, …)         │
│  • Vision grounding when tree is sparse                 │
│  • Recovery playbook only on verify failures            │
└───────────────────────┬─────────────────────────────────┘
                        │ StepRequest / StepResponse
┌───────────────────────▼─────────────────────────────────┐
│  Android — perception + motor                           │
│  • ScreenClassifier → structured ScreenState            │
│  • IntentResolver → a11y → memory → vision at exec time │
│  • ActionExecutor → a11y → memory → deep link           │
│  • GestureHelper → human motor (jitter, curves, dwell)  │
│  • OutcomeVerifier + DeviceMemoryStore → learning loop  │
└─────────────────────────────────────────────────────────┘
```

## Design principles

1. **Autonomy = intent + perceive + verify + remember.** The brain plans WHAT (intents); the phone binds WHERE at execution time (a11y → memory → vision), verifies, then persists the learned coord to `DeviceMemoryStore`. Hardcoding bypasses perception; learning is perception that persists.
2. **No phone-side choreography** — the agent loop does not force swipes or coordinate maps before the brain sees the screen. In particular, `enter_reels` uses **navigate/deep link only** — never a pager swipe.
3. **Intent over atoms** — prefer `{"action":"intent","params":{"name":"next_reel"}}` over hardcoded x,y taps.
4. **Execution-time binding** — `target_id` and coordinates are resolved from the *current* accessibility tree, not stale LLM output.
5. **Vision-first on ambiguity** — Reels, comments, and low-confidence screens attach screenshots by default. First bind on a fresh device *must* go through `/agent/ground`.
6. **Verify + retry** — every tap runs through `OutcomeVerifier`. Unverified intent taps force a fresh screenshot and re-ground (max 2 retries per anchor per session).
7. **Playbook as recovery** — deterministic steps run only after verify failures or action loops, not every session.
8. **Human motor** — gestures use Bézier paths, jitter, and variable duration to avoid robotic uniformity.

## Intent vocabulary

| Intent | Phone behavior |
|--------|----------------|
| `enter_reels` | a11y bottom-nav → device memory → Instagram deep link → **one controlled swipe LEFT** if still on home. **Never swipe RIGHT** (opens Stories). |
| `watch_reel` / `dwell` | human-paced wait |
| `open_comments` | a11y `comments_icon` → memory `comments_icon` → `/agent/ground` with fresh screenshot |
| `engage_comments` | a11y `comment_heart` row → memory `comment_heart` → `/agent/ground` with `row_index` |
| `next_reel` | human swipe up on the right rail (only vertical motor allowed in reels work) |
| `go_back` | press back |
| `check_inbox` / `open_profile` | navigate tab |

See `brain/app/agent/intents.py` and `shared/action_protocol.md`.

## Migration from hardcoded paths

| Removed | Replaced by |
|---------|-------------|
| `ensureReelsOpen()` preflight pager swipe | `intent enter_reels` = a11y → memory → deep link |
| `AgentController` preflight `swipeFeedPager("left")` fallback | Nothing — pager swipes are banned in the `enter_reels` path |
| `ActionExecutor.navigate("reels")` pager-swipe fallback | Deep link only; failure escalates to `IntentResolver` + vision |
| Bottom-nav % coordinates (10/30/50/70/90) | a11y labels + `DeviceMemoryStore` (`nav_reels`) |
| Comments icon 93%×52% | `IntentResolver.open_comments` + vision (`comments_icon`) |
| `DeviceMemoryStore` bug that mapped `like_comment` → `comments_icon` | Correct schema: `like_comment` → `comment_heart` |
| Memory storing `0,0` when `target_id` was used | `VerifiedStepReporter` resolves element center before `bump()` |
| Cold-start with empty phone SQLite | `AgentController` pulls `GET /learning/memory/{device_id}` on session start |
| Screen-state overrides in AgentController | Trust `ScreenClassifier` + brain guards |
| Routine playbook kickstart | Recovery-only playbook in router |

## Learning loop

Verified steps feed `DeviceMemoryStore` (phone) and `/learning/trajectory` (brain).
Both use the **same `ui_key` schema** end-to-end: `nav_reels`, `nav_home`,
`comments_icon`, `comment_heart`, `action_like_story`, etc. The IntentResolver
attaches `ui_key` to every resolved tap so memory learns a stable, addressable key.

On session start `AgentController.runGoal()` calls `GET /learning/memory/{device_id}`
and hydrates the phone SQLite store. Successful tap targets are reused before
requesting vision, so second runs on the same device use memory hits and fall
through to `/agent/ground` only when the UI actually changed.

## Vision grounding (`POST /agent/ground`)

When accessibility and device memory cannot bind a tap, the phone sends a **fresh screenshot**
to the brain. **Gemma 3 vision** (local vLLM — no OpenAI) returns pixel coordinates.

Binding order: **a11y element → device memory → `/agent/ground`**.

Env: `FRIDAY_VISION_ALWAYS_INSTAGRAM=true`, `FRIDAY_GROUNDING_ENABLED=true`.
