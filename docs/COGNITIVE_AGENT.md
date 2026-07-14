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
│  • IntentResolver → bind targets at execution time      │
│  • ActionExecutor → a11y → device memory → pager swipe  │
│  • GestureHelper → human motor (jitter, curves, dwell)  │
│  • OutcomeVerifier + DeviceMemoryStore → learning loop  │
└─────────────────────────────────────────────────────────┘
```

## Design principles

1. **No phone-side choreography** — the agent loop does not force swipes or coordinate maps before the brain sees the screen.
2. **Intent over atoms** — prefer `{"action":"intent","params":{"name":"next_reel"}}` over hardcoded x,y taps.
3. **Execution-time binding** — `target_id` and coordinates are resolved from the *current* accessibility tree, not stale LLM output.
4. **Vision-first on ambiguity** — Reels, comments, and low-confidence screens attach screenshots by default.
5. **Playbook as recovery** — deterministic steps run only after verify failures or action loops, not every session.
6. **Human motor** — gestures use Bézier paths, jitter, and variable duration to avoid robotic uniformity.

## Intent vocabulary

| Intent | Phone behavior |
|--------|----------------|
| `enter_reels` | navigate → memory → feed pager swipe → deep link |
| `watch_reel` / `dwell` | human-paced wait |
| `open_comments` | a11y match → memory → request screenshot |
| `engage_comments` | like_comment on next heart |
| `next_reel` | human swipe up |
| `go_back` | press back |
| `check_inbox` / `open_profile` | navigate tab |

See `brain/app/agent/intents.py` and `shared/action_protocol.md`.

## Migration from hardcoded paths

| Removed | Replaced by |
|---------|-------------|
| `ensureReelsOpen()` preflight swipe | Brain `intent enter_reels` |
| Bottom-nav % coordinates (10/30/50/70/90) | a11y labels + `DeviceMemoryStore` |
| Comments icon 93%×52% | `IntentResolver.open_comments` + vision |
| Screen-state overrides in AgentController | Trust `ScreenClassifier` + brain guards |
| Routine playbook kickstart | Recovery-only playbook in router |

## Learning loop

Verified steps feed `DeviceMemoryStore` (phone) and `/learning/trajectory` (brain). Successful tap targets for `nav_reels`, `comments_icon`, and `like_comment` are reused before requesting vision.
