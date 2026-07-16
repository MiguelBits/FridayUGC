# Human teach mode

Learn Instagram Reels skills from your demos on a real phone. Phase 1 focuses on **open_comments**.

## Flow

1. **Record** — you tap comments on the phone; we capture before/after screenshots and your label.
2. **Store** — `ok` demos with coords aggregate into a stable `comments_icon` (median x,y) under `data/teach/`.
3. **Replay** — taps **only** the taught coord (no vision / no Y-offset guessing) and scores with strict comments-sheet text checks.
4. **Agent** — `motor_resolver` prefers TeachStore coords for `comments_icon` when `n_ok >= 3`, then LearningStore memory.

Ads (`ad`), share sheet (`wrong_sheet`), and browser/cookie traps (`trap`) are **never** stored as success.

## Commands (Git Bash, from `brain/`)

```bash
cd brain && source .venv/Scripts/activate && adb devices
```

```bash
cd brain && source .venv/Scripts/activate && python -m adb.teach record --skill open_comments --open-reels --count 10
```

```bash
cd brain && source .venv/Scripts/activate && python -m adb.teach show --skill open_comments
```

```bash
cd brain && source .venv/Scripts/activate && python -m adb.teach replay --skill open_comments --trials 10
```

```bash
cd brain && source .venv/Scripts/activate && pytest tests/test_teach.py -q
```

## Record UX

Per episode:

1. BEFORE screenshot (+ UI texts if uiautomator works)
2. You open comments on the phone
3. Enter when done (`s` skip, `a` mark ad + swipe, `q` quit)
4. AFTER screenshot
5. Confirm: **Comments opened correctly? [Y/n]** — Enter or `Y` = `ok`; `N` then pick `fail` / `ad` / `wrong_sheet` / `trap`
6. For `ok`: click the BEFORE image (tkinter) or type `x,y` / `92% 52%`

## How the agent uses the skill

After enough `ok` demos, running the normal ADB loop with `reels_comment_likes` will tap the taught `comments_icon` first (TeachStore → device_memory). Failures during teach do **not** bump fail counts on good coords.

## Layout

```
brain/data/teach/
  episodes/*.json
  shots/*_before.png / *_after.png
  skills/open_comments__<device_id>.json
  replay/<timestamp>/report.json
```
