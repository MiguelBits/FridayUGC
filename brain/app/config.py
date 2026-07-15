from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment / .env.

    Everything here is overridable via env vars prefixed with FRIDAY_.
    """

    model_config = SettingsConfigDict(
        env_prefix="FRIDAY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM provider selection ---
    llm_provider: str = "mock"  # gemma_vllm | ollama | mock

    # Agent step engine: legacy (direct LLM) | maf (Microsoft Agent Framework)
    agent_engine: str = "legacy"  # legacy | maf

    # MAF — see docs/MAF_SETUP.md
    # maf_backend: ollama (local Gemma, free) | azure (cloud, pay per token)
    maf_backend: str = "ollama"  # ollama | azure
    maf_model: str = ""
    maf_azure_endpoint: str = ""
    maf_azure_api_key: str = ""
    maf_api_version: str = "preview"  # Responses API v1 — not dated chat-completions versions

    # Gemma 4 via vLLM (OpenAI-compatible)
    gemma_base_url: str = "http://127.0.0.1:8000/v1"
    gemma_model: str = "google/gemma-4-12b-it"
    gemma_api_key: str = "friday-local-key"

    # Ollama
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:e4b"

    # Sampling
    temperature: float = 0.7
    max_tokens: int = 512

    # LLM resilience
    llm_timeout: float = 120.0
    llm_max_retries: int = 2
    llm_retry_backoff_s: float = 0.5

    # Session run traces (agent observability)
    runs_data_path: str = ""

    # Auth: the token the Android agent must present.
    api_token: str = "change-me-to-a-long-random-string"

    # Persona
    persona: str = "lorena"

    # Safety
    approval_actions: str = "post,comment,dm,follow,unfollow"
    read_only_blocked_actions: str = (
        "post,comment,dm,follow,unfollow,like,like_story,like_comment,save,type"
    )

    # --- UGC session engagement caps (per agent run) ---
    ugc_likes_max: int = 25
    ugc_story_likes_max: int = 12
    ugc_reels_max: int = 35
    ugc_comments_max: int = 8
    ugc_dms_max: int = 10
    ugc_follows_max: int = 3
    ugc_saves_max: int = 5

    @property
    def approval_action_set(self) -> set[str]:
        return {a.strip() for a in self.approval_actions.split(",") if a.strip()}

    @property
    def read_only_blocked_set(self) -> set[str]:
        return {a.strip() for a in self.read_only_blocked_actions.split(",") if a.strip()}

    # --- TTS (OmniVoice on AWS GPU) ---
    tts_provider: str = "mock"  # mock | omnivoice
    voice_enabled: bool = False  # FRIDAY_VOICE_ENABLED — /voice/speak + phone playback
    omnivoice_url: str = "http://127.0.0.1:8001"
    omnivoice_instruct: str = "female, low pitch, calm, warm, american accent"

    # --- Cloud gallery (S3 or local dev manifest) ---
    gallery_backend: str = "local"  # local | s3
    gallery_s3_bucket: str = ""
    gallery_s3_manifest_key: str = "gallery/manifest.json"
    gallery_s3_region: str = "us-east-1"
    gallery_local_path: str = ""  # empty = bundled brain/data/gallery/manifest.json

    # --- Vision (multimodal model sees gallery frames) ---
    vision_enabled: bool = True
    vision_model: str = "google/gemma-3-12b-it"
    vision_base_url: str = ""  # empty = use gemma_base_url
    vision_api_key: str = ""  # empty = use gemma_api_key
    vision_max_side_px: int = 768

    # --- Inbox / DM policy (not every message gets a reply) ---
    inbox_max_replies_per_user_per_day: int = 2
    inbox_comment_max_per_user_per_day: int = 2
    inbox_max_replies_global_per_day: int = 40
    inbox_min_hours_between_same_user: float = 4.0
    inbox_skip_low_effort: bool = True
    inbox_low_effort_reply_probability: float = 0.35
    inbox_reply_pace_probability: float = 0.65
    inbox_ledger_path: str = ""

    # --- Autonomous operator (SQLite day planner + quotas) ---
    operator_db_path: str = ""
    operator_enabled: bool = True
    operator_stuck_session_ttl_min: int = 45
    operator_circuit_breaker_failures: int = 8

    # --- Gallery queue (curated posting schedule) ---
    gallery_queue_path: str = ""

    # --- Learning loop (verified trajectories + device memory) ---
    learning_db_path: str = ""
    vision_on_ambiguous: bool = True
    vision_ambiguous_element_threshold: int = 12
    vision_always_instagram: bool = True
    grounding_enabled: bool = True

    # --- RAG / gallery retrieval (local SQLite index, Azure-ready embeddings) ---
    rag_enabled: bool = True
    rag_gallery_top_k: int = 20
    rag_caption_top_k: int = 5
    rag_index_path: str = ""  # empty = brain/data/gallery/rag_index.db
    rag_hybrid_enabled: bool = True  # BM25 + vector fusion (raglite-style)
    rag_hybrid_alpha: float = 0.6  # weight on vector score vs lexical (0–1)

    # mock | ollama | gemma_vllm | openai | azure
    embedding_provider: str = "mock"
    embedding_model: str = "nomic-embed-text"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_dimensions: int = 384
    embedding_timeout: float = 60.0

    # Azure OpenAI embeddings (set FRIDAY_EMBEDDING_PROVIDER=azure)
    embedding_azure_endpoint: str = ""
    embedding_azure_api_key: str = ""
    embedding_azure_deployment: str = ""  # e.g. text-embedding-3-small
    embedding_azure_api_version: str = "2024-10-21"


@lru_cache
def get_settings() -> Settings:
    return Settings()
