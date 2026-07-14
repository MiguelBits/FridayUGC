# Microsoft Agent Framework — Friday brain

Use [Microsoft Agent Framework (MAF)](https://github.com/microsoft/agent-framework) as the agent step engine. The Android phone and action protocol stay the same.

## Recommended: local Gemma + Azure ready (hybrid)

| Mode | Cost | Use for |
|------|------|---------|
| **MAF + Ollama (Gemma)** | **Free** (your PC GPU/RAM) | Daily dev + phone testing |
| **MAF + Azure OpenAI** | Pay per token | Prove cloud / demo to others |
| **Legacy + Ollama** | Free | Same as Ollama without MAF |
| **AWS g5 + Gemma (later)** | ~$1/hr when running | Cheapest self-hosted cloud at scale |

Keep your **Azure Foundry project** — you don't need to call it every day. Switch `FRIDAY_MAF_BACKEND=azure` only when you want a cloud test.

## Architecture

```
Android phone ──POST /agent/step──▶ FastAPI brain
                                      │
                    FRIDAY_AGENT_ENGINE=maf
                                      │
                                      ▼
                         Microsoft Agent Framework
                         (Agent + AgentSession)
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
   FRIDAY_MAF_BACKEND=ollama                    FRIDAY_MAF_BACKEND=azure
   Ollama + Gemma (local, free)                Azure OpenAI (cloud proof)
```

- **`legacy`**: mock / Ollama / self-hosted Gemma via vLLM (no MAF)
- **`maf`**: MAF `Agent.run()` with per-session memory (`session_id` from the phone)

## Install (Python 3.10–3.12 required — not 3.14)

On Windows, install Python 3.12 from https://www.python.org/downloads/ then:

```bash
cd brain && rm -rf .venv && py -3.12 -m venv .venv && source .venv/Scripts/activate && pip install -r requirements.txt -r requirements-maf.txt
```

Install Ollama: https://ollama.com — then:

```bash
ollama pull gemma3:12b
```

## Option A — Local Gemma via MAF (recommended, free)

`brain/.env`:

```env
FRIDAY_AGENT_ENGINE=maf
FRIDAY_MAF_BACKEND=ollama
FRIDAY_MAF_MODEL=gemma3:12b
FRIDAY_OLLAMA_MODEL=gemma3:12b
FRIDAY_API_TOKEN=your-brain-token
```

## Option B — Azure cloud (when you want to prove cloud)

Deploy `gpt-4o-mini` in Foundry → **View deployments**, then:

```env
FRIDAY_AGENT_ENGINE=maf
FRIDAY_MAF_BACKEND=azure
FRIDAY_MAF_MODEL=google--gemma-4-e4b-it
FRIDAY_MAF_AZURE_ENDPOINT=https://miguel-5595-resource.openai.azure.com/
FRIDAY_MAF_AZURE_API_KEY=your-key
FRIDAY_MAF_API_VERSION=preview
FRIDAY_API_TOKEN=your-brain-token
```

Switch back to `FRIDAY_MAF_BACKEND=ollama` anytime to stop Azure charges.

## Option C — Legacy Ollama (no MAF)

```env
FRIDAY_AGENT_ENGINE=legacy
FRIDAY_LLM_PROVIDER=ollama
FRIDAY_OLLAMA_MODEL=gemma3:12b
```

## Run locally

```bash
cd brain && source .venv/Scripts/activate && uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Health should show `"agent_engine": "maf"` (and Ollama must be running for local mode).

## Point the Android app

Build APK with your PC LAN IP (same Wi‑Fi):

```bash
cd android && ./gradlew assembleDebug -Pfriday.brainUrl=http://YOUR_PC_IP:8080 -Pfriday.apiToken=YOUR_BRAIN_TOKEN
```

## Later: self-hosted Gemma on AWS

```env
FRIDAY_AGENT_ENGINE=legacy
FRIDAY_LLM_PROVIDER=gemma_vllm
FRIDAY_GEMMA_BASE_URL=http://your-gpu-box:8000/v1
```

Or keep MAF and point `FRIDAY_MAF_BACKEND=ollama` at a remote Ollama/vLLM OpenAI-compatible endpoint.
