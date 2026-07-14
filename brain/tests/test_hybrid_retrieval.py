"""Hybrid BM25 + vector retrieval tests."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("FRIDAY_LLM_PROVIDER", "mock")
os.environ.setdefault("FRIDAY_API_TOKEN", "test-token")
os.environ.setdefault("FRIDAY_EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("FRIDAY_RAG_ENABLED", "true")
os.environ.setdefault("FRIDAY_RAG_HYBRID_ENABLED", "true")

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.gallery.schemas import GalleryAsset  # noqa: E402
from app.retrieval.gallery import asset_document, sync_gallery_index  # noqa: E402
from app.retrieval.vector_store import GalleryVectorStore  # noqa: E402


def _asset(asset_id: str, *, pillar: str, description: str) -> GalleryAsset:
    return GalleryAsset(
        id=asset_id,
        description=description,
        pillar=pillar,  # type: ignore[arg-type]
        vision_summary=description,
        vibe=pillar,
        tags=[pillar],
    )


@pytest.fixture
def rag_db(tmp_path, monkeypatch):
    db_path = tmp_path / "rag_index.db"
    monkeypatch.setenv("FRIDAY_RAG_INDEX_PATH", str(db_path))
    get_settings.cache_clear()
    from app.retrieval import embeddings

    embeddings.get_embedding_client.cache_clear()
    yield db_path
    get_settings.cache_clear()
    embeddings.get_embedding_client.cache_clear()


def test_hybrid_lexical_boosts_keyword_match(rag_db, monkeypatch):
    monkeypatch.setenv("FRIDAY_RAG_HYBRID_ALPHA", "0.5")
    get_settings.cache_clear()

    assets = [
        _asset("gym_1", pillar="gym", description="squat rack leg day mirror"),
        _asset("food_1", pillar="food", description="protein bowl meal prep kitchen"),
    ]
    asyncio.run(sync_gallery_index(assets))

    store = GalleryVectorStore()
    client_mod = __import__("app.retrieval.embeddings", fromlist=["get_embedding_client"])
    client = client_mod.get_embedding_client()

    async def _run() -> list[tuple[str, float]]:
        query = "leg day squat gym workout"
        vector = await client.embed_one(query)
        return store.search_hybrid(vector, query, top_k=2)

    ranked = asyncio.run(_run())
    assert ranked
    assert ranked[0][0] == "gym_1"


def test_vector_only_when_hybrid_disabled(rag_db, monkeypatch):
    monkeypatch.setenv("FRIDAY_RAG_HYBRID_ENABLED", "false")
    get_settings.cache_clear()

    assets = [
        _asset("gym_1", pillar="gym", description="squat rack leg day mirror"),
        _asset("food_1", pillar="food", description="protein bowl meal prep kitchen"),
    ]
    asyncio.run(sync_gallery_index(assets))
    store = GalleryVectorStore()
    assert store.search_lexical("leg day", top_k=5)
    assert store.count() == 2


def test_fts_indexed_on_sync(rag_db):
    assets = [_asset("gym_1", pillar="gym", description="deadlift platform chalk")]
    asyncio.run(sync_gallery_index(assets))
    store = GalleryVectorStore()
    hits = store.search_lexical("deadlift chalk", top_k=3)
    assert hits
    assert hits[0][0] == "gym_1"
    doc = asset_document(assets[0])
    assert "deadlift" in doc
