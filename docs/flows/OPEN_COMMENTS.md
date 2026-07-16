# Flow: open_comments

**ID:** `open_comments`  
**Goal:** From Reels viewer, open the **comments sheet** (not share/repost).  
**Status:** Primary gap — deterministic layer + probe learning.

## Preconditions

- On **Reels tab** (not Home `Para ti` / `For you`)
- Organic reel — **not** `Patrocinado` / Sponsored
- If the publication has no remix/repost/republish affordance and shows ad CTAs → **swipe away**
- `reels_tab_opened == 1`
- Optional short dwell already done (`reel_dwell_done`)

## Steps

| # | Kind | Action | Target | Notes |
|---|------|--------|--------|-------|
| 1 | resolve | pick coords | `comments_icon` | Order below |
| 2 | motor | `tap` | `(x,y)` + `ui_key=comments_icon` | Settle ~650–1200 ms |
| 3 | verify | classify surface | screenshot + a11y | Must be comments, not share |

### Coordinate resolution order

1. **Device memory** — verified successes for this `device_id` (`ui_key=comments_icon`)
2. **Vision ground** — Gemma, constrained to comments band
3. **Deterministic % fallback** — `(0.90 W, 0.52 H)` then probe offsets if needed

### Comments band (reject share)

- X > 78% of width (right rail)
- Y in **[48%, 55.5%]** of height
- Reject rail taps with Y ≥ **56%** (share/repost zone)

## Success criteria (strict)

Comments open is **verified only if**:

- A11y comments signals (`Reply`, `Add a comment…`, etc.), **or**
- Screenshot heuristic: light bottom sheet covering ~40%+ of frame **and** not share/repost signals

`change_score` alone is **not** enough (share sheet also changes UI).

## Failure criteria

| Outcome | Detection | Next action |
|---------|-----------|-------------|
| Share / repost sheet | `wrong_sheet` / share signals / dark share list | `press back`, bump retry, try higher Y (closer to like) |
| No change | score ~0, still reels | Retry with alternate Y offset |
| 3 unverified taps | tick retry streak | Abandon reel → swipe next |

## Session flags

| Event | Flags |
|-------|-------|
| Verified open | `comments_sheet_open=1`, `comment_likes_phase=in_comments` |
| Unverified / wrong | do **not** set `comments_sheet_open`; may set `wrong_sheet=share` |

## Probe

```bash
python -m brain.adb.probe_comments --trials 20 --out data/probes/comments_open
```

Writes per-step screenshots and learns which Y offsets open comments on this device.
