"""Safe JSON extraction from LLM outputs — never raises to callers."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def extract_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return {}


def parse_model(raw: str, model: type[T], *, fallback: T | None = None) -> tuple[T | None, list[str]]:
    """Parse LLM text into a Pydantic model. Returns (instance, warnings)."""
    warnings: list[str] = []
    data = extract_json_object(raw)
    if not data:
        warnings.append("llm_parse_failed")
        return fallback, warnings
    try:
        return model.model_validate(data), warnings
    except ValidationError as exc:
        warnings.append(f"llm_validation_failed: {exc.error_count()} errors")
        return fallback, warnings


def coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    return t.strip()


def repair_inline_action(action: str) -> tuple[str, dict[str, Any]]:
    """Fix model output like swipe{\"direction\": \"up\"}."""
    raw = (action or "wait").strip()
    if "{" not in raw:
        return raw.split()[0].lower(), {}
    name, rest = raw.split("{", 1)
    frag = "{" + rest.rstrip()
    if not frag.endswith("}"):
        frag += "}"
    try:
        parsed = json.loads(frag)
        if isinstance(parsed, dict):
            return name.strip().lower(), parsed
    except json.JSONDecodeError:
        pass
    params: dict[str, Any] = {}
    direction = re.search(r"direction\s*:\s*['\"]?(\w+)['\"]?", frag, re.I)
    if direction:
        params["direction"] = direction.group(1).lower()
    return name.strip().lower(), params
