# Friday UGC

**Friday** is an autonomous UGC (user-generated content) operator for the **Lorena Mor** AI persona. A **remote brain** (FastAPI + Gemma on AWS GPU via vLLM) plans each step; a **USB ADB executor** on the same PC reads the screen and performs taps, scrolls, and posts on Instagram (`@itslorenamor`).

```
You / schedule ──▶ Gemma brain (local or AWS GPU) ──▶ ADB executor (PC) ──USB──▶ Phone / Instagram
                        ▲                                    │
                        └──────── observe / tick / result ───┘
```

## What this repo contains

| Path | Role |
|------|------|
| [`brain/`](brain/) | Python FastAPI service — persona, agent loop, RAG, learning/eval |
| [`brain/adb/`](brain/adb/) | USB ADB executor — screencap, motor actions, thin tick loop |
| [`infra/`](infra/) | AWS deploy — CloudFormation GPU box + Docker Compose for vLLM |
| [`shared/`](shared/) | JSON action protocol between executor and brain |
| [`docs/`](docs/) | Setup, architecture, safety, ADB migration, portfolio mapping |
| [`.github/workflows/`](.github/workflows/) | CI — brain pytest on push |

## Eval results

Last run: **2026-07-15** (local, `FRIDAY_LLM_PROVIDER=mock` — no GPU required).

### Brain (pytest)

| Suite | What it validates |
|-------|-------------------|
| Agent eval harness | Frozen IG scenarios + router-level vision/reels entry |
| ADB executor / loop | Mocked subprocess + tick loop, read_only, circuit breaker |
| Retrieval / RAG | Gallery + caption index, hybrid BM25+vector fusion |
| Learning loop | Verified trajectories, device memory, eval reports |
| Smoke / API | Endpoints, inbox evaluate, protocol wiring |
| Perception + tick | Screen parsing, reels routing, thin-client tick |

Reproduce:

```bash
cd brain && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
FRIDAY_LLM_PROVIDER=mock FRIDAY_API_TOKEN=test-token pytest -q
```

CI runs the full brain suite on every push to `brain/**` (see [`.github/workflows/brain-ci.yml`](.github/workflows/brain-ci.yml)).

## Architecture highlights

- **Remote brain / local hands** — PC captures screenshots via ADB; brain returns one JSON action per tick.
- **Server-side guards** — read-only mode, session budgets, and approval gates for `post`, `comment`, `dm`, `follow`.
- **RAG** — gallery curation + caption style retrieval ([`brain/app/retrieval/`](brain/app/retrieval/)).
- **Observability** — per-step session traces at `GET /runs`, `GET /runs/{id}`, `GET /runs/metrics`.
- **Mock LLM** — full pipeline in CI without GPU (`FRIDAY_LLM_PROVIDER=mock`).

Deeper docs: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/TECH_STACK.md`](docs/TECH_STACK.md), [`docs/ADB_MIGRATION.md`](docs/ADB_MIGRATION.md).

## Quick start

Full walkthrough: [`docs/SETUP_GUIDE.md`](docs/SETUP_GUIDE.md).

```bash
# 1. Brain — local smoke test (no GPU)
cd brain
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit FRIDAY_API_TOKEN
FRIDAY_LLM_PROVIDER=mock uvicorn app.main:app --reload --port 8080

# 2. Phone — enable USB debugging, verify: adb devices

# 3. ADB executor (from repo root, brain venv active)
export FRIDAY_API_TOKEN=your-token
python -m brain.adb.run --goal "Open Instagram and scroll Reels" --mode read_only
```

See [`brain/adb/README.md`](brain/adb/README.md) for flags and troubleshooting.

Copy [`brain/.env.example`](brain/.env.example) to `brain/.env`. Never commit `.env`, `apitoken.txt`, or `*.pem`.

## Safety

Instagram automation on a real account carries **ban risk**. Friday defaults to **approval-gated posting** and **human-like pacing**. Read [`docs/SAFETY_AND_BANS.md`](docs/SAFETY_AND_BANS.md) and test on a throwaway account first.

## Portfolio / hiring

| Artifact | Location |
|----------|----------|
| Tools & job-post mapping | [`docs/TECH_STACK.md`](docs/TECH_STACK.md) |
| Role mapping (PT) | [`docs/JOB_APPLICATION_MAPPING.md`](docs/JOB_APPLICATION_MAPPING.md) |
| Case study template | [`docs/CASE_STUDY.md`](docs/CASE_STUDY.md) |
| ADB migration record | [`docs/ADB_MIGRATION.md`](docs/ADB_MIGRATION.md) |
| Example session trace | [`brain/data/runs/example_session.json`](brain/data/runs/example_session.json) |

## License

Persona assets (Lorena Mor) belong to the owner. Code is provided for portfolio and evaluation purposes.
