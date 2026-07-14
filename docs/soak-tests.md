# Physical device soak tests

These gates define "viable" for the local-first autonomous operator prototype.

## Prerequisites

- Throwaway Instagram account on a physical Android device
- Brain running at `http://<pc-ip>:8080` with `FRIDAY_AGENT_ENGINE=legacy`
- Accessibility enabled for Friday UGC
- APK built with matching `BRAIN_URL` and `API_TOKEN`
- Ollama model ready (`gemma4:e4b`; optional `FRIDAY_VISION_MODEL=gemma3:12b`)

## 24-hour soak

1. `POST /operator/day-plan` with `mode=full`
2. On phone: enable autonomous schedule (syncs plan + starts FGS polling)
3. Verify micro-sessions run across the day (not one burst)
4. Verify daily quotas are not exceeded (`GET /operator/status`)
5. Tap notification **Stop** — operator must pause within one step
6. `POST /operator/resume` — next due task should claim successfully
7. Kill app process mid-session — checkpoint stored; resume on next claim
8. No HTTP 500s from `/agent/step` during the soak

## 7-day soak

- No duplicate posts (`/gallery/record-post` idempotency receipts)
- No stuck sessions older than `FRIDAY_OPERATOR_STUCK_SESSION_TTL_MIN`
- No unhandled brain errors in run traces (`GET /runs/metrics`)
- Circuit breaker should trip after 8 consecutive action failures, then recover next day

## Posting pipeline checks

- `POST /gallery/scan` — all planned assets `status=ok`
- Gallery sync worker downloads due assets to MediaStore
- One reel post with caption/location marks asset posted only after success screen
- One story post from queue
- Retry with same `idempotency_key` returns `deduplicated=true`

## Engagement checks

- Reels navigation (tab + deep link fallback)
- Comment-sheet recognition with screenshot vision
- 10-reel comment-like routine within session budget
- Feed engagement micro-session respects per-session caps

## CI gates (automated)

```bash
cd brain && source .venv/Scripts/activate && pytest -q
```

```bash
export JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" && export PATH="$JAVA_HOME/bin:$PATH" && cd android && ./gradlew testDebugUnitTest assembleDebug
```
