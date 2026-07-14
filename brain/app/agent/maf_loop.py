"""Agent step decisions via Microsoft Agent Framework (MAF).

Local Ollama (Gemma) or Azure OpenAI through agent-framework.
Docs: https://github.com/microsoft/agent-framework
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..config import get_settings
from ..persona import get_persona
from .actions import StepRequest, StepResponse
from .prompt import apply_guards, build_step_user_prompt, fallback_step_data, parse_step_json, response_from_json

# Phone sends step history in StepRequest — no need to accumulate MAF session memory
# (avoids 2k+ token prompts and ~27s Ollama calls per step).
_sessions: dict[str, Any] = {}


def _require_maf() -> None:
    try:
        import agent_framework  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Microsoft Agent Framework not installed. Run: "
            "pip install agent-framework-core agent-framework-openai"
        ) from exc


@lru_cache
def _build_chat_client():
    _require_maf()
    from agent_framework.openai import OpenAIChatClient

    s = get_settings()
    kwargs: dict[str, Any] = {}
    model = s.maf_model or s.ollama_model
    if model:
        kwargs["model"] = model

    if s.maf_backend.lower() == "ollama":
        # Local Ollama (Gemma) — OpenAI-compatible, no Azure token cost
        kwargs["base_url"] = f"{s.ollama_base_url.rstrip('/')}/v1"
        kwargs["api_key"] = "ollama"
    else:
        # Azure OpenAI — cloud proof / production inference
        if s.maf_azure_endpoint:
            kwargs["azure_endpoint"] = s.maf_azure_endpoint
        if s.maf_azure_api_key:
            kwargs["api_key"] = s.maf_azure_api_key
        if s.maf_api_version:
            kwargs["api_version"] = s.maf_api_version
    return OpenAIChatClient(**kwargs)


@lru_cache
def _build_agent(persona_key: str):
    from agent_framework import Agent

    persona = get_persona(persona_key)
    instructions = (
        f"{persona.system_prompt}\n\n"
        "You are the Friday UGC operator brain. Each turn you output exactly ONE JSON action "
        "for the Android phone to execute. Never output prose outside JSON."
    )
    return Agent(
        client=_build_chat_client(),
        name="FridayUGCOperator",
        instructions=instructions,
    )


def _get_session(session_id: str, persona_key: str):
    if session_id in _sessions:
        return _sessions[session_id]
    agent = _build_agent(persona_key)
    session = agent.create_session()
    _sessions[session_id] = session
    return session


async def decide_maf(req: StepRequest, persona_key: str = "lorena") -> StepResponse:
    """One agent step using Microsoft Agent Framework (fresh session each step)."""
    _require_maf()
    agent = _build_agent(persona_key)
    session = agent.create_session()
    prompt = build_step_user_prompt(req)

    result = await agent.run(prompt, session=session)
    raw = result.text if hasattr(result, "text") else str(result)
    data = parse_step_json(raw)
    if not data.get("action"):
        data = fallback_step_data(req)
    resp = response_from_json(data)
    return apply_guards(req, resp)
