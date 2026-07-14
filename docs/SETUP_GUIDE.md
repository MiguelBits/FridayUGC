# Friday UGC — Setup Guide (start here)

This is the end-to-end walkthrough. Realistic time: ~1 focused evening for the first run.
There is no true "one file and it works" for an autonomous phone agent — but this gets you to
**deploy once, install one APK, flip 3 toggles, run.**

## Overview of the 4 phases

1. Test the brain locally (no GPU) — 10 min.
2. Deploy the brain to AWS GPU — 30–45 min.
3. Build + install the Android APK — 20 min.
4. Grant permissions, test on a throwaway IG, then point at `@itslorenamor`.

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

## Phase 2 — Deploy the brain to AWS GPU

See `AWS_DEPLOY.md`. Short version:

```bash
aws cloudformation deploy --template-file infra/cloudformation/friday-brain.yaml \
  --stack-name friday-brain --capabilities CAPABILITY_IAM \
  --parameter-overrides KeyName=YOUR_KEY MyIpCidr=YOUR_IP/32 HfToken=hf_xxx \
  FridayApiToken=YOUR_LONG_TOKEN GemmaModel=google/gemma-4-12b-it
```

Grab the `BrainApiUrl` output — that's what the phone talks to.

## Phase 3 — Build the Android APK

Two options (see `ANDROID_BUILD.md`):

- **CI (recommended):** push to GitHub → run the `android-apk` workflow with your `brain_url` →
  download the APK from the run's Artifacts.
- **Local:** open `android/` in Android Studio, then
  `./gradlew assembleDebug -Pfriday.brainUrl=YOUR_URL -Pfriday.apiToken=YOUR_TOKEN`.

## Phase 4 — Install + run on the phone

1. Sideload the APK (enable "install unknown apps" for your browser/file manager).
2. Open Friday → **Enable Accessibility** → turn on "Friday UGC Agent".
3. Settings → Battery → set Friday to **Unrestricted**.
4. Tap **Check brain** (should say OK).
5. Type a goal like *"Open Instagram and scroll the feed for 30 seconds"* → **Run goal**.
6. Test engagement/posting on a **throwaway account first**. Only then point at `@itslorenamor`.

---

## The full "Friday runs my account" loop

- **Voice command:** speak/type a goal → brain plans → phone executes → Friday narrates aloud.
- **Autonomous:** schedule goals (WorkManager on device, or a cron that calls the brain). Keep
  `post/comment/dm/follow` approval-gated until you trust it. See `SAFETY_AND_BANS.md`.

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| Brain: unreachable | Check `BRAIN_URL`, AWS security group allows your IP, port 8080 open |
| Nothing happens on screen | Accessibility service not enabled, or app blocks a11y |
| Stuck repeating an action | Loop detection triggers a recovery; if persistent, the UI changed |
| IG login checkpoint | Expected on automation; log in manually once, avoid aggressive pacing |
