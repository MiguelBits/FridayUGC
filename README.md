# Friday UGC

**Friday** is an autonomous UGC (user-generated content) operator for the **Lorena Mor** AI persona. A **remote brain** (FastAPI + Gemma on AWS GPU via vLLM) plans each step; an **Android accessibility agent** reads the screen and executes taps, scrolls, and posts on Instagram (`@itslorenamor`).

```
You / schedule ──▶ Gemma brain (AWS GPU) ──▶ Android agent (Accessibility) ──▶ Instagram
                        ▲                                    │
                        └──────── screen state / result ─────┘
```

## What this repo contains

| Path | Role |
|------|------|
| [`brain/`](brain/) | Python FastAPI service — persona, agent loop, RAG, voice, learning/eval |
| [`android/`](android/) | Kotlin agent — Accessibility executor, brain client, voice, foreground service |
| [`infra/`](infra/) | AWS deploy — CloudFormation GPU box + Docker Compose for vLLM |
| [`shared/`](shared/) | JSON action protocol between phone and brain |
| [`docs/`](docs/) | Setup, architecture, safety, AWS/Android build, portfolio mapping |
| [`.github/workflows/`](.github/workflows/) | CI — brain pytest on push; signed APK build |

## Eval results

Last run: **2026-07-14** (local, `FRIDAY_LLM_PROVIDER=mock` — no GPU required).

### Brain (pytest)

| Suite | Tests | Passed | What it validates |
|-------|------:|-------:|-------------------|
| **Agent eval harness** | 7 | 7 | Frozen IG screen scenarios → correct action, guards, approval gates |
| Retrieval / RAG | 8 | 8 | Gallery + caption index, embedding ranking, pillar diversity |
| Learning loop | 5 | 5 | Verified trajectories, device memory, eval reports |
| Smoke / API | 20 | 20 | Endpoints, inbox evaluate, protocol wiring |
| Perception + navigation | 16 | 16 | Screen parsing, reels routing, protocol parity |
| **Total** | **64** | **64** | |

**Agent scenario coverage** (`brain/tests/fixtures/agent_scenarios/`):

| Scenario | Expected behavior |
|----------|-------------------|
| `opens_instagram_from_launcher` | Launch Instagram when not foreground |
| `scrolls_when_instagram_open` | Scroll feed when IG is open |
| `navigate_to_inbox` | Open inbox from home |
| `read_only_blocks_like` | Read-only mode blocks like mutations |
| `budget_blocks_extra_likes` | Session like budget enforced server-side |
| `post_requires_approval` | Post action requires human approval |

Reproduce:

```bash
cd brain && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
FRIDAY_LLM_PROVIDER=mock FRIDAY_API_TOKEN=test-token pytest -q
```

Agent eval only:

```bash
cd brain && FRIDAY_LLM_PROVIDER=mock FRIDAY_API_TOKEN=test-token pytest tests/test_agent_eval.py -v
```

### Android (unit tests)

| Suite | Tests | Passed |
|-------|------:|-------:|
| ScreenClassifier | 5 | 5 |
| ScreenValidator | 4 | 4 |
| OutcomeVerifier | 4 | 4 |
| AgentNotificationManager | 1 | 1 |
| **Total** | **14** | **14** |

Reproduce:

```bash
cd android && ./gradlew testDebugUnitTest
```

CI runs the full brain suite on every push to `brain/**` (see [`.github/workflows/brain-ci.yml`](.github/workflows/brain-ci.yml)).

## Architecture highlights

- **Remote brain / local hands** — phone sends accessibility tree; brain returns one JSON action per step.
- **Server-side guards** — read-only mode, session budgets, and approval gates for `post`, `comment`, `dm`, `follow` (not prompt-only).
- **RAG** — gallery curation + caption style retrieval over a local SQLite vector index ([`brain/app/retrieval/`](brain/app/retrieval/)).
- **Observability** — per-step session traces at `GET /runs`, `GET /runs/{id}`, `GET /runs/metrics`.
- **Mock LLM** — full pipeline in CI without GPU (`FRIDAY_LLM_PROVIDER=mock`).

Deeper docs: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/TECH_STACK.md`](docs/TECH_STACK.md), [`docs/CASE_STUDY.md`](docs/CASE_STUDY.md).

## Quick start

Full walkthrough: [`docs/SETUP_GUIDE.md`](docs/SETUP_GUIDE.md).

```bash
# 1. Brain — local smoke test (no GPU)
cd brain
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit FRIDAY_API_TOKEN
FRIDAY_LLM_PROVIDER=mock uvicorn app.main:app --reload

# 2. Android APK — see docs/ANDROID_BUILD.md or GitHub Actions workflow
# 3. AWS GPU deploy — see docs/AWS_DEPLOY.md
```

Copy [`brain/.env.example`](brain/.env.example) to `brain/.env`. Never commit `.env`, `apitoken.txt`, or `*.pem`.

## Safety

Instagram automation on a real account carries **ban risk**. Friday defaults to **approval-gated posting** and **human-like pacing**. Read [`docs/SAFETY_AND_BANS.md`](docs/SAFETY_AND_BANS.md) and test on a throwaway account first.

## Portfolio / hiring

| Artifact | Location |
|----------|----------|
| Tools & job-post mapping | [`docs/TECH_STACK.md`](docs/TECH_STACK.md) |
| Role mapping (PT) | [`docs/JOB_APPLICATION_MAPPING.md`](docs/JOB_APPLICATION_MAPPING.md) |
| Case study template | [`docs/CASE_STUDY.md`](docs/CASE_STUDY.md) |
| Microsoft Agent Framework | [`docs/MAF_SETUP.md`](docs/MAF_SETUP.md) |
| Example session trace | [`brain/data/runs/example_session.json`](brain/data/runs/example_session.json) |

## License

Persona assets (Lorena Mor) belong to the owner. Code is provided for portfolio and evaluation purposes.
