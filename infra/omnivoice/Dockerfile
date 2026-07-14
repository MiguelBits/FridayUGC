# OmniVoice TTS sidecar — shares the GPU box with vLLM.
# On g5.xlarge you may need to lower vLLM gpu-memory-utilization to ~0.55
# so both Gemma 4 and OmniVoice fit, or run TTS on CPU (slow).
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    OMNIVOICE_DEVICE=cuda:0

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY serve.py .

RUN pip3 install --no-cache-dir \
    fastapi uvicorn pydantic \
    torch==2.8.0+cu128 torchaudio==2.8.0+cu128 \
    --extra-index-url https://download.pytorch.org/whl/cu128 \
    && pip3 install --no-cache-dir omnivoice

EXPOSE 8001
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8001"]
