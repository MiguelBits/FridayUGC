# Instagram API transport (instagrapi)

Friday drives Instagram through **instagrapi** (private API). Primary workflow: **scroll reels + like comments**.

## Quick start

```bash
cd brain && pip install -r requirements.txt
cp .env.example .env
# Set FRIDAY_IG_USERNAME + FRIDAY_IG_PASSWORD
FRIDAY_LLM_PROVIDER=mock python -m brain.instagram.run login
FRIDAY_LLM_PROVIDER=mock python -m brain.instagram.run doctor
```

### One shot (scroll reels + like comments)

Dry run first:

```bash
FRIDAY_LLM_PROVIDER=mock python -m brain.instagram.run reels --dry-run --reels-max 5
```

Live:

```bash
FRIDAY_LLM_PROVIDER=mock python -m brain.instagram.run reels --reels-max 10 --mode full
```

### Scheduled infra (operator daemon)

Plan today (reels-only sessions):

```bash
FRIDAY_LLM_PROVIDER=mock python -m brain.instagram.run plan --sessions 4 --mode full
```

Run daemon (claims tasks from SQLite operator queue):

```bash
FRIDAY_LLM_PROVIDER=mock python -m brain.instagram.run daemon
```

Check budgets + queue:

```bash
FRIDAY_LLM_PROVIDER=mock python -m brain.instagram.run status
```

## What runs today

| Component | Status |
|-----------|--------|
| Reels scroll + comment likes | **Yes** |
| Daily caps (operator ledger) | **Yes** |
| Operator plan + daemon | **Yes** (reels-only) |
| Post / inbox / stories | Not yet |

## Daily caps

Tracked in `brain/data/operator/state.db`:

- `comment_likes` — default cap 100/day
- `reels_scrolled` — default cap 40/day

Session stops when either cap is hit.

## VPS / cookies

Use `FRIDAY_IG_SESSION_JSON` + `FRIDAY_IG_PROXY` for datacenter IPs. See instagram-ai-agent cookie flow.

## ADB

Deprecated. Use this module instead.
