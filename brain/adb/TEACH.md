# Human teach mode

**First flow:** put likes on comments in a Reel — with chained screenshots at every step.

## What we are recording

Per reel you (human) do this on the phone; we ask and screenshot each step:

```
on Reels
  → open comments     BEFORE=reel  AFTER=proof comments open
  → like a comment    BEFORE=that proof  AFTER=after like
  → scroll comments   BEFORE=previous AFTER
  → like another      BEFORE=previous AFTER
  → close comments    BEFORE=previous AFTER  (Back)
  → next reel         BEFORE=previous AFTER  (swipe up)
```

The AFTER of step N is copied as the BEFORE of step N+1 — so we keep evidence we got to comments and move forward from that same picture.

Tap targets (`open_comments`, `like_comment`) also ask you to click the BEFORE image for coords. Scroll / close / next are evidence-only.

## Commands (Git Bash, from `brain/`)

```bash
cd brain && source .venv/Scripts/activate && adb devices
```

Full reel flow (default):

```bash
cd brain && source .venv/Scripts/activate && python -m adb.teach record --skill full_loop --count 10 --likes 2
```

Open-comments only:

```bash
cd brain && source .venv/Scripts/activate && python -m adb.teach record --skill open_comments --count 10
```

```bash
cd brain && source .venv/Scripts/activate && python -m adb.teach show --skill open_comments
```

```bash
cd brain && source .venv/Scripts/activate && python -m adb.teach show --skill like_comment
```

```bash
cd brain && source .venv/Scripts/activate && python -m adb.teach replay --skill open_comments --trials 10
```

```bash
cd brain && source .venv/Scripts/activate && pytest tests/test_teach.py -q
```

## Per-step UX

1. Show / reuse BEFORE screenshot  
2. You act on the phone  
3. Enter when done (`s` skip, `a` ad, `q` quit)  
4. Capture AFTER (evidence)  
5. Confirm Y/n  
6. For taps: click BEFORE where you tapped  

## Layout

```
brain/data/teach/
  episodes/*.json          # each step (skill + parent_id + chained_from)
  shots/*_before.png / *_after.png
  skills/open_comments__<device_id>.json
  skills/like_comment__<device_id>.json
```
