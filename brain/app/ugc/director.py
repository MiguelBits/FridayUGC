from __future__ import annotations

import json

from ..llm import ChatMessage, get_llm
from ..persona import get_persona
from ..retrieval.captions import retrieve_caption_examples
from . import safety
from .archetypes import archetype_prompt_block, pick_archetype
from .schemas import (
    CaptionRequest,
    CaptionResponse,
    GenPromptRequest,
    GenPromptResponse,
    PlanRequest,
    PlanResponse,
)

# Reusable negative tail for UGC-block generation prompts (from DIRECTOR_FLOW).
NEGATIVE_TAIL = (
    "No spoken dialogue. No lip-sync. No nudity, no underwear reveal, no lingerie, no explicit "
    "touching, no erotic action, no see-through fabric, no sheer clothing, no translucent fabric, "
    "no wardrobe change from reference, no exaggerated anatomy, no identity drift, no face morphing, "
    "no wrong eye color, no extra fingers, no phone visible, no device in hands, no third hand, "
    "no text overlays, no watermark. Pale green eyes unchanged every frame. Fabric remains opaque "
    "in every frame."
)


def _extract_json(text: str) -> dict:
    """Best-effort parse of a JSON object from a model completion."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


async def make_plan(req: PlanRequest, persona_key: str = "lorena") -> PlanResponse:
    persona = get_persona(persona_key)
    llm = get_llm()
    archetype = pick_archetype(pillar_hint=req.notes or "", lane_hint=req.lane_hint or "")
    arch_block = archetype_prompt_block(archetype)
    user = (
        "RETURN_PLAN_JSON\n"
        "Design one Instagram reel for this reference. Respond with a JSON object with keys: "
        "lane (A-E), type, cta (1-3), code, on_screen_text (<=8 words, ALL CAPS), hook (one line), "
        "caption (<=22 words, Lorena voice, ends with the CTA).\n\n"
        f"Reference: {req.ref_description}\n"
        f"Type hint: {req.type_hint or 'auto'}\n"
        f"Lane hint: {req.lane_hint or 'auto'}\n"
        f"Notes: {req.notes or 'none'}"
        f"{arch_block}"
    )
    raw = await llm.chat(
        [ChatMessage("system", persona.system_prompt), ChatMessage("user", user)],
        json_mode=True,
    )
    data = _extract_json(raw)
    caption = safety.sanitize_dialogue(str(data.get("caption", "")))
    return PlanResponse(
        lane=data.get("lane", "A"),
        type=data.get("type", req.type_hint or "silent"),
        cta=int(data.get("cta", 1)),
        code=data.get("code", f"*{data.get('lane','A')}({data.get('type','silent')}){data.get('cta',1)}*"),
        on_screen_text=str(data.get("on_screen_text", "")).upper(),
        hook=data.get("hook", ""),
        caption=caption,
        warnings=safety.audit(caption),
    )


async def make_caption(req: CaptionRequest, persona_key: str = "lorena") -> CaptionResponse:
    persona = get_persona(persona_key)
    llm = get_llm()
    cta_map = {1: "comment bait", 2: "DM me", 3: "link/list in description 👇"}
    rag_examples, rag_warnings, _hits = await retrieve_caption_examples(
        req.context,
        cta=req.cta,
    )
    archetype = pick_archetype(pillar_hint=req.context[:120])
    arch_block = archetype_prompt_block(archetype)
    examples_block = ""
    if rag_examples:
        lines = "\n".join(f"  - {ex!r}" for ex in rag_examples)
        examples_block = (
            "\nMatch the tone and rhythm of these REAL posted captions (do not copy verbatim):\n"
            f"{lines}\n"
        )
    user = (
        "RETURN_CAPTION\n"
        f"Write ONE Instagram caption (<= {req.max_words} words) in Lorena's voice for this. "
        f"End with a {cta_map[req.cta]} style call to action. No hashtags spam (max 2).\n\n"
        f"Context: {req.context}"
        f"{examples_block}"
        f"{arch_block}"
    )
    raw = await llm.chat(
        [ChatMessage("system", persona.system_prompt), ChatMessage("user", user)]
    )
    caption = safety.sanitize_dialogue(raw.strip())
    warnings = rag_warnings + safety.audit(caption)
    return CaptionResponse(caption=caption, rag_examples=rag_examples, warnings=warnings)


async def make_gen_prompt(req: GenPromptRequest, persona_key: str = "lorena") -> GenPromptResponse:
    persona = get_persona(persona_key)
    code = f"*{req.lane}({req.type}){req.cta}*"
    setting = req.setting or "cozy bedroom, round wall mirror, warm neutral tones"

    # Deterministic UGC-block shell (the user's filter-safe default), filled from the request.
    prompt = (
        "Use the provided image as the first frame. Keep the subject's identity, face, outfit, room, "
        "lighting, and body proportions consistent. "
        f"{persona.identity_anchor}\n\n"
        f"Realistic handheld vertical phone video, 9:16, {req.duration_s} seconds. Front-facing camera "
        "POV. No phone visible. No device in hands. The adult subject wears the opaque outfit from the "
        f"reference — fabric stays fully opaque, same coverage as the photo, no wardrobe change — "
        f"styled like a private UGC try-on clip. {req.ref_description}\n\n"
        f"{setting}, subtle handheld camera shake, authentic smartphone compression, realistic skin "
        "texture, no beauty filter, no studio lighting. Motion slow, casual, believable — like a real "
        "creator checking the outfit before posting.\n\n"
        f"{NEGATIVE_TAIL}"
    )
    prompt = safety.sanitize_visual(prompt)
    return GenPromptResponse(prompt=prompt, code=code, warnings=safety.audit(prompt))
