#!/usr/bin/env python3
"""Minimal OmniVoice HTTP server for Friday's assistant TTS.

Run on the AWS GPU box (port 8001). Requires: pip install omnivoice torch torchaudio
See https://github.com/MiguelBits/OmniVoice

  OMNIVOICE_DEVICE=cuda:0 uvicorn serve:app --host 0.0.0.0 --port 8001
"""
from __future__ import annotations

import io
import os

import torch
import torchaudio
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel, Field

app = FastAPI(title="Friday OmniVoice TTS")

_model = None
_device = os.environ.get("OMNIVOICE_DEVICE", "cuda:0")


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    instruct: str = Field(
        default="female, low pitch, calm, american accent",
        description="Voice design attributes (OmniVoice voice-design mode).",
    )
    num_step: int = 16


def _load_model():
    global _model
    if _model is not None:
        return _model
    from omnivoice import OmniVoice

    dtype = torch.float16 if "cuda" in _device else torch.float32
    _model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=_device, dtype=dtype)
    return _model


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "device": _device}


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest) -> Response:
    model = _load_model()
    audio = model.generate(text=req.text, instruct=req.instruct, num_step=req.num_step)
    buf = io.BytesIO()
    torchaudio.save(buf, audio[0], 24000, format="wav")
    return Response(content=buf.getvalue(), media_type="audio/wav")
