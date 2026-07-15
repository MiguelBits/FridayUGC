# Friday UGC — Setup Guide (start here)

This is the end-to-end walkthrough. Realistic time: ~1 focused evening for the first run.

## Overview of the 4 phases

1. Test the brain locally (no GPU) — 10 min.
2. Deploy the brain to AWS GPU (optional) — 30–45 min.
3. Connect phone via USB ADB — 10 min.
4. Run the ADB executor on a throwaway IG account, then `@itslorenamor`.

---

## Phase 1 — Brain locally (no GPU)

```bash
cd brain
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # keep FRIDAY_LLM_PROVIDER=mock for now
export FRIDAY_LLM_PROVIDER=mock FRIDAY_API_TOKEN=test-token
pytest -q                       # all smoke tests should pass
uvicorn app.main:app --reload --port 8080
```

Verify:

```bash
curl -s localhost:8080/health
curl -s -X POST localhost:8080/ugc/caption -H "Authorization: Bearer test-token" \
  -H "content-type: application/json" -d '{"context":"dressing room black ribbed dress","cta":1}'
```

## Phase 2 — Deploy the brain to AWS GPU (optional)

See `AWS_DEPLOY.md`. The ADB executor can target a remote brain via `--brain-url`.

## Phase 3 — USB ADB setup

1. Install [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) (`adb` on PATH).
2. On the phone: **Developer options** → enable **USB debugging**.
3. Connect USB; accept the RSA fingerprint prompt on the phone.
4. Verify:

```bash
adb devices
```

Expected: one device with state `device` (not `unauthorized`).

Optional session prep (executor runs this automatically):

```bash
adb shell settings put system screen_off_timeout 2147483647 && adb shell svc power stayon usb && adb shell input keyevent KEYCODE_WAKEUP
```

## Phase 4 — Run the ADB executor

From repo root with brain venv active:

```bash
export FRIDAY_API_TOKEN=your-token
python -m brain.adb.run \
  --brain-url http://127.0.0.1:8080 \
  --goal "Open Instagram and scroll Reels" \
  --mode read_only \
  --max-steps 20
```

Comment-likes routine (requires vision grounding):

```bash
FRIDAY_GROUNDING_ENABLED=true python -m brain.adb.run \
  --routine reels_comment_likes \
  --mode full \
  --max-steps 60
```

Flags: see [`brain/adb/README.md`](../brain/adb/README.md).

Test engagement/posting on a **throwaway account first**. Only then point at `@itslorenamor`.

---

## The full "Friday runs my account" loop

- **Manual goal:** pass `--goal` to the ADB executor; brain plans; PC executes via ADB.
- **Autonomous:** schedule executor runs (cron) or use the brain operator API. Keep
  `post/comment/dm/follow` approval-gated until you trust it. See `SAFETY_AND_BANS.md`.

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| Brain: unreachable | Check `--brain-url`, AWS security group, port 8080 |
| `adb devices` empty | Replug USB; enable USB debugging; try another cable |
| `unauthorized` | Accept RSA prompt on phone |
| Black screenshot | Unlock phone; avoid IG login/checkpoint screens |
| Nothing taps | Check read_only mode; verify brain returns `tap` with x,y |
| Multiple devices | Pass `--serial` from `adb devices -l` |
