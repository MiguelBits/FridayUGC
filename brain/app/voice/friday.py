from __future__ import annotations

from ..llm import ChatMessage, get_llm
from ..ugc.schemas import VoiceRequest, VoiceResponse

# Friday's assistant voice is NOT Lorena's voice. Friday is a competent, warm, concise
# female assistant (think F.R.I.D.A.Y.). She narrates and confirms; she does not perform.
FRIDAY_VOICE_SYSTEM = (
    "You are Friday, a calm, competent, warm female voice assistant that operates the Lorena Mor "
    "Instagram account. Speak in short spoken-style sentences (1-2 sentences, <= 30 words). "
    "Be concrete and reassuring. Do not use Lorena's flirty persona — that voice is only for "
    "captions and on-screen content. Never read out long lists; summarize."
)


async def reply(req: VoiceRequest) -> VoiceResponse:
    llm = get_llm()
    user = (
        "RETURN_VOICE\n"
        f"User said: {req.user_text!r}\n"
        f"Situation: {req.situation or 'general'}\n"
        "Give Friday's short spoken reply."
    )
    text = await llm.chat(
        [ChatMessage("system", FRIDAY_VOICE_SYSTEM), ChatMessage("user", user)],
        max_tokens=80,
    )
    return VoiceResponse(reply=text.strip())
