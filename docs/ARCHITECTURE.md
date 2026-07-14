# Friday UGC — Architecture

## One-paragraph summary

Friday is a **remote-brain / local-hands** agent. A **Gemma 4** model runs on an **AWS GPU** box
(served by vLLM, OpenAI-compatible) behind a small **FastAPI brain**. Your **Android phone** runs a
Kotlin agent that uses the **Accessibility API** to read the Instagram UI and perform taps, scrolls,
and typing. The phone sends screen state to the brain each step and executes the single action the
brain returns. Friday also has a **female voice** (on-device TTS) and can run on voice command or
autonomously on a schedule.

## Diagram

```mermaid
flowchart LR
  subgraph Phone["OnePlus / Android (hands + eyes)"]
    A11y["FridayAccessibilityService\n(read tree + gestures)"]
    Reader["ScreenReader\n(tree -> indexed elements)"]
    Exec["ActionExecutor\n(tap/scroll/type/...)"]
    Ctrl["AgentController\n(observe->decide->act)"]
    Voice["VoiceManager\n(female TTS)"]
    IG["Instagram\n@itslorenamor"]
    Ctrl --> Reader --> A11y
    Ctrl --> Exec --> A11y --> IG
    Ctrl --> Voice
  end

  subgraph AWS["AWS GPU (brain)"]
    API["FastAPI brain\n/agent/step /ugc/* /voice/reply"]
    Director["UGC director\n(lanes/types/CTA + safety)"]
    Persona["Lorena persona pack"]
    vLLM["vLLM serving Gemma 4"]
    API --> Director --> Persona
    API --> vLLM
  end

  Ctrl <-->|"HTTPS + Bearer token\nStepRequest / StepResponse"| API
```

## Request lifecycle (agent step)

1. `AgentController` asks `FridayAccessibilityService` for the current screen.
2. `ScreenReader` flattens the accessibility tree into a compact indexed element list.
3. The phone POSTs `StepRequest` to `/agent/step` with the goal, screen, and recent history.
4. The brain builds a prompt (Lorena system prompt + screen + action spec) and asks Gemma 4 for
   **one action** as JSON.
5. The brain enforces server-side safety (real-account mutations → `approval_required=true`).
6. The phone executes the action via `ActionExecutor`, waits a human-like delay, and repeats.

## Content lifecycle (creation, not UI driving)

`/ugc/plan`, `/ugc/caption`, `/ugc/prompt` produce a reel plan, an Instagram caption, or a
Seedance/Marketing-Studio generation prompt — all in Lorena's voice, run through the safety
word-swap layer. These are the "think like a UGC creator at human speed" endpoints.

## Why this split

- The phone can't run a big model well; AWS can. Gemma 4 12B on a g5 gives strong reasoning.
- The brain is model-agnostic (`LLMClient`): swap Gemma for another endpoint without touching
  persona/director/agent code.
- The account stays safe because approval + pacing live on both sides.

## Component map

| Concern | Lives in |
|--------|----------|
| Persona / voice / rules | `brain/app/persona/` |
| UGC creation | `brain/app/ugc/` |
| Phone-driving decisions | `brain/app/agent/` |
| Model access | `brain/app/llm/` |
| Screen read + gestures | `android/.../ScreenReader.kt`, `ActionExecutor.kt` |
| Loop + pacing + approval | `android/.../AgentController.kt` |
| Deploy | `infra/` |
