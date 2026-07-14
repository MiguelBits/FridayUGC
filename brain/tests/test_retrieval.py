"""RAG gallery retrieval tests — mock embeddings, no network."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

os.environ.setdefault("FRIDAY_LLM_PROVIDER", "mock")
os.environ.setdefault("FRIDAY_API_TOKEN", "test-token")
os.environ.setdefault("FRIDAY_EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("FRIDAY_RAG_ENABLED", "true")

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.gallery.queue import GalleryQueueStore  # noqa: E402
from app.gallery.schemas import GalleryAsset  # noqa: E402
from app.retrieval.captions import (  # noqa: E402
    caption_document,
    retrieve_caption_examples,
    sync_caption_index,
)
from app.retrieval.embeddings import MockEmbeddingClient  # noqa: E402
from app.retrieval.gallery import (  # noqa: E402
    asset_document,
    build_curation_query,
    retrieve_assets_for_curation,
    sync_gallery_index,
)
from app.retrieval.vector_store import CaptionVectorStore, GalleryVectorStore, cosine_similarity  # noqa: E402


def _asset(
    asset_id: str,
    *,
    pillar: str = "gym",
    description: str = "",
    vision_summary: str = "",
    vibe: str = "",
) -> GalleryAsset:
    return GalleryAsset(
        id=asset_id,
        description=description or f"{pillar} asset",
        pillar=pillar,  # type: ignore[arg-type]
        vision_summary=vision_summary or description,
        vibe=vibe or pillar,
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


def test_mock_embeddings_rank_similar_text():
    client = MockEmbeddingClient(dimensions=128)

    async def _run() -> None:
        gym_vec = (await client.embed(["leg day squat rack mirror gym energy"]))[0]
        outfit_vec = (await client.embed(["dressing room black dress try-on mirror"]))[0]
        gym_query = (await client.embed(["weekly leg day gym content plan"]))[0]
        assert cosine_similarity(gym_query, gym_vec) > cosine_similarity(gym_query, outfit_vec)

    asyncio.run(_run())


def test_sync_gallery_index_updates_store(rag_db):
    assets = [
        _asset("a1", pillar="gym", description="squat rack leg day"),
        _asset("a2", pillar="outfit", description="mirror dress try-on"),
    ]
    updated, warnings = asyncio.run(sync_gallery_index(assets))
    assert updated == 2
    assert warnings == []
    store = GalleryVectorStore()
    assert store.count() == 2

    updated_again, _ = asyncio.run(sync_gallery_index(assets))
    assert updated_again == 0


def test_retrieve_prefers_matching_pillar(rag_db, monkeypatch):
    monkeypatch.setenv("FRIDAY_RAG_GALLERY_TOP_K", "2")
    get_settings.cache_clear()

    assets = [
        _asset("gym_1", pillar="gym", description="squat rack leg day mirror"),
        _asset("gym_2", pillar="gym", description="rdl deadlift gritty gym"),
        _asset("outfit_1", pillar="outfit", description="dressing room dress try-on"),
        _asset("food_1", pillar="food", description="protein bowl meal prep"),
        _asset("life_1", pillar="lifestyle", description="miami balcony coffee"),
    ]
    asyncio.run(sync_gallery_index(assets))

    selected, warnings, hits = asyncio.run(
        retrieve_assets_for_curation(
            assets,
            notes="Heavy gym week — leg day focus",
            days_ahead=7,
            max_posts_per_day=2,
        )
    )
    assert len(selected) == 2
    assert any(a.pillar == "gym" for a in selected)
    assert any("rag_retrieved_2_of_5_assets" == w for w in warnings)
    assert any("rag_scores:" in w for w in warnings)
    assert len(hits) == 2
    assert all(hit.kind == "gallery" for hit in hits)
    assert all(hit.score > 0 for hit in hits)


def test_build_curation_query_includes_notes():
    query = build_curation_query(notes="Miami outfit push", days_ahead=3, max_posts_per_day=2)
    assert "Miami outfit push" in query
    assert "3 days" in query


def test_asset_document_includes_vision_fields():
    asset = _asset(
        "x1",
        pillar="gym",
        description="human hint",
        vision_summary="mirror squat rack",
        vibe="gritty leg day",
    )
    asset.visual_tags = ["mirror", "gym"]
    doc = asset_document(asset)
    assert "mirror squat rack" in doc
    assert "gritty leg day" in doc
    assert "visual_tags=mirror, gym" in doc


@pytest.fixture
def caption_queue_db(tmp_path, monkeypatch, rag_db):
    queue_path = tmp_path / "queue.db"
    monkeypatch.setenv("FRIDAY_GALLERY_QUEUE_PATH", str(queue_path))
    get_settings.cache_clear()
    yield queue_path
    get_settings.cache_clear()


def _seed_posted_caption(queue: GalleryQueueStore, *, item_id: str, caption: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with queue._conn() as conn:
        conn.execute(
            """
            INSERT INTO queue_items(
                item_id, asset_ids, format, caption, hashtags, location,
                scheduled_at, timezone, status, retry_count, idempotency_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'posted', 0, ?, ?)
            """,
            (
                item_id,
                json.dumps([f"asset_{item_id}"]),
                "reel",
                caption,
                json.dumps(["#legday"]),
                "",
                "2026-01-01T12:00:00+00:00",
                "America/New_York",
                item_id,
                now,
            ),
        )


def test_sync_caption_index_from_posted_queue(caption_queue_db):
    queue = GalleryQueueStore()
    _seed_posted_caption(
        queue,
        item_id="cap_gym_1",
        caption="Two leg days back to back. Tell me no.",
    )
    _seed_posted_caption(
        queue,
        item_id="cap_outfit_1",
        caption="Wrong mirror. Right dress. Yes or no.",
    )

    updated, warnings = asyncio.run(sync_caption_index())
    assert updated == 2
    assert CaptionVectorStore().count() == 2
    assert warnings == []


def test_retrieve_caption_examples_prefers_matching_context(caption_queue_db, monkeypatch):
    monkeypatch.setenv("FRIDAY_RAG_CAPTION_TOP_K", "2")
    get_settings.cache_clear()

    queue = GalleryQueueStore()
    _seed_posted_caption(
        queue,
        item_id="cap_gym_1",
        caption="Two leg days back to back. Tell me no.",
    )
    _seed_posted_caption(
        queue,
        item_id="cap_outfit_1",
        caption="Wrong mirror. Right dress. Yes or no.",
    )
    asyncio.run(sync_caption_index())

    examples, warnings, hits = asyncio.run(
        retrieve_caption_examples("leg day gym reel squat rack", cta=1)
    )
    assert len(examples) >= 1
    assert any("leg day" in ex.lower() for ex in examples)
    assert any("rag_caption_retrieved" in w for w in warnings)
    assert any("rag_caption_scores:" in w for w in warnings)
    assert hits[0].kind == "caption"


def test_caption_document_includes_pillar():
    doc = caption_document(
        "Mirror check before posting.",
        pillar="gym",
        post_format="reel",
        hashtags=["#legday"],
    )
    assert "pillar=gym" in doc
    assert "Mirror check" in doc
