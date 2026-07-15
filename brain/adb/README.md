# Friday ADB executor

USB-tethered **hands** for the Friday brain. The PC runs this loop; the phone is only a display controlled via `adb`.

## Prerequisites

- Android phone with **USB debugging** enabled
- [platform-tools](https://developer.android.com/tools/releases/platform-tools) on `PATH`
- Brain running locally or on AWS (`FRIDAY_API_TOKEN` in `.env`)

```bash
adb devices
```

Expected: one line with state `device` (not `unauthorized`).

## Quick start

From repo root (with brain venv activated):

```bash
cd brain && source .venv/bin/activate
FRIDAY_LLM_PROVIDER=mock FRIDAY_API_TOKEN=test-token uvicorn app.main:app --host 0.0.0.0 --port 8080
```

In another terminal:

```bash
export FRIDAY_API_TOKEN=your-token
python -m brain.adb.run --goal "Open Instagram and scroll Reels" --mode read_only --max-steps 20
```

Comment-likes routine with vision grounding:

```bash
FRIDAY_GROUNDING_ENABLED=true python -m brain.adb.run \
  --routine reels_comment_likes --mode full --max-steps 60
```

## Flags

| Flag | Purpose |
|------|---------|
| `--brain-url` | Brain base URL (default `http://127.0.0.1:8080`) |
| `--token` | Bearer token (`FRIDAY_API_TOKEN`) |
| `--goal` | Task goal string |
| `--mode read_only` | Blocks like/comment/post/dm/follow/type |
| `--autonomous` | Skip terminal approval prompts |
| `--routine` | Call `POST /ugc/routine` first |
| `--serial` | Pick device when multiple are connected |
| `--max-steps` | Step limit (default 40) |

## Session prep

On start the executor runs:

```bash
adb shell settings put system screen_off_timeout 2147483647
adb shell svc power stayon usb
adb shell input keyevent KEYCODE_WAKEUP
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `unauthorized` in `adb devices` | Accept RSA prompt on phone; replug USB |
| Black screenshot | Unlock phone; avoid IG login/checkpoint screens |
| `Multiple devices` | Pass `--serial` from `adb devices -l` |
| Tick timeouts | Check brain URL/token; run `curl localhost:8080/health` |
| Clipboard type fails | OEM-specific; retry or use ASCII-only text |

## Tests

```bash
cd brain && FRIDAY_LLM_PROVIDER=mock FRIDAY_API_TOKEN=test-token pytest tests/test_adb_executor.py tests/test_adb_loop.py -q
```
