# Friday UGC brain — API container (the LLM itself runs separately in vLLM).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8080

# The brain talks to Gemma 4 (vLLM) over FRIDAY_GEMMA_BASE_URL.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
