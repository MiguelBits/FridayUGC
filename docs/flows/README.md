# Instagram agentic flows (ADB brain)

Deterministic + learned choreography for Friday’s USB ADB navigator.

## Goal (current slice)

| Step | Status |
|------|--------|
| Open Reels tab | Tall-phone fix: deeplink + center tab `(0.50, 0.955)` |
| Open comments sheet | Fragile — vision often hits share/repost |
| Like 3 comments (scroll sheet) | Next |
| Close comments → next reel → repeat | Next |

## How the brain decides today

```
observe → verify last → plan (routine FSM | router) → ground target → execute → settle
```

- **Open Reels** is a **motor** step (`navigate` / deeplink) — no vision.
- **Open comments** is a **ground_tap** on `comments_icon` — vision + band check + memory.
- Wrong rail icon (share / “Repost” / paper plane) opens a **share sheet**, which can look like “UI changed” and poison session state.

## Flow docs

| Doc | Purpose |
|-----|---------|
| [INSTAGRAM_REELS_UI.md](INSTAGRAM_REELS_UI.md) | Right-rail layout, screenshot meaning, failure modes |
| [OPEN_REELS.md](OPEN_REELS.md) | Deterministic enter-Reels flow |
| [OPEN_COMMENTS.md](OPEN_COMMENTS.md) | Comments open: band, verify, share rejection |
| [COMMENT_LIKES_LOOP.md](COMMENT_LIKES_LOOP.md) | Full per-reel loop (target choreography) |
| [LEARNING_LOOP.md](LEARNING_LOOP.md) | Success/fail memory from real device runs |

## Code map

| Path | Role |
|------|------|
| `brain/app/agent/flows/` | Flow definitions + surface heuristics |
| `brain/app/agent/routines.py` | `reels_comment_likes` FSM |
| `brain/app/agent/grounding.py` | Vision coords + comments band |
| `brain/app/agent/verifier.py` | Success/fail after each action |
| `brain/adb/probe_comments.py` | 20× probe: open reels → open comments + step screenshots |

## Probe (learn open-comments)

With phone unlocked, Instagram installed, brain optional:

```bash
cd brain && source .venv/bin/activate
python -m brain.adb.probe_comments --trials 20 --out data/probes/comments_open
```

Each trial writes `before/`, `after/`, and `report.json` with pass/fail and which Y offset worked.
