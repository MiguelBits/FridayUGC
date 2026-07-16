# Learning loop — learn from actions, not guesses

## Problem

ADB posts trajectories with `verified="unknown"`, so grounding exemplars and device memory rarely update from live runs. Vision keeps re-guessing the rail and can relearn the **wrong** icon (share).

## Design

```
action → settle → after screenshot
              ↓
      surface classifier (a11y + pixels)
              ↓
     success | wrong_sheet | no_change
              ↓
   update device_memory + grounding_examples
   update flow offset preference
   rewrite trajectory verified status
```

## Memory keys

| Key | Payload |
|-----|---------|
| `comments_icon` | Best `(x,y)` with `success_count` / `fail_count` |
| `comments_icon@offset` | Probe-learned Y fraction that worked |
| `wrong_sheet` | Last wrong surface name for recovery |

## Rules

1. **Only verified comments opens** write to `comments_icon` success memory.
2. **Wrong sheet** increments fail and **never** stores those coords as comments.
3. After failure, prefer **higher** Y offset toward like (smaller Y) — share is below.
4. Probe runs (`probe_comments`) are the supervised dataset for a new device/IG version.
5. Routine ticks consume memory before vision before % fallback.

## Evaluation

Probe `report.json`:

```json
{
  "trials": 20,
  "open_reels_ok": 20,
  "open_comments_ok": 14,
  "wrong_sheet": 4,
  "no_change": 2,
  "best_y_frac": 0.52,
  "trials_detail": [...]
}
```

Human review: open `after/` screenshots — comments sheet = pass; share/repost = fail.

## Wiring

| Component | Role |
|-----------|------|
| `brain/app/agent/flows/surface.py` | Pixel + text surface labels |
| `brain/app/agent/flows/memory.py` | Record success/fail coords |
| `brain/app/agent/verifier.py` | Strict comments verify |
| `brain/adb/probe_comments.py` | Offline 20× learning trials |
| `LearningStore` | Persist exemplars when `verified=="verified"` |
