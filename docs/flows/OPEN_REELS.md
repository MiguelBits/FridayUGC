# Flow: open_reels

**ID:** `open_reels`  
**Goal:** Leave home/other tabs and land on Reels viewer.  
**Status:** Deterministic — tall-phone coords (center Reels tab).

## Preconditions

- Instagram installed (`com.instagram.android`)
- Device unlocked, USB debugging authorized
- Not stuck on login / checkpoint

## Steps

| # | Kind | Action | Params | Settle |
|---|------|--------|--------|--------|
| 1 | motor | `navigate` | `tab=reels`, `ui_key=nav_reels` | ~2800 ms |

Executor behavior (`brain/adb/executor.py` + `brain/adb/nav.py`):

1. `am start` deeplink `instagram://reels`
2. Tap bottom-nav Reels at **`(0.50 W, 0.955 H)`** on tall phones (aspect ≥ 2.1, e.g. 1440×3216)
3. Standard phones: `(0.50 W, 0.965 H)`
4. Probe retries also try legacy X `0.30` if center miss (older IG: Reels second from left)

Current IG bottom nav (probe device): `Home | Search | Reels | Shop | Profile` — Reels is **center**, not second.

## Success criteria

Any of:

- Activity contains `clips` / `reel` (not profile)
- Classifier `screen_type == reels_viewer`
- Soft: meaningful UI change after navigate (legacy)

Session flags (set when navigate runs — verify separately):

- `reels_tab_opened = 1`
- `reels_entry_attempts += 1`

## Failure / recovery

| Failure | Recovery |
|---------|----------|
| Still on home feed tabs | Retry navigate with next X/Y candidate; do not vision-tap bottom nav repeatedly |
| Story viewer | `press back` then re-enter |
| Other app | `open_app` Instagram then navigate |

## Code

- Planner: `comment_likes_plan` → navigate when `reels_tab_opened==0`
- Router: `_needs_reels_entry` / `_reels_entry_response`
- Motor: `brain/adb/nav.py` `nav_xy("reels", …)` / `nav_reels_candidates`
