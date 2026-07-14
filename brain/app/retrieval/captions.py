from __future__ import annotations

import logging

from ..config import get_settings
from ..gallery.queue import GalleryQueueStore
from ..gallery.schemas import RetrievalHit
from ..gallery.store import GalleryStore
from .embeddings import get_embedding_client
from .gallery import doc_hash
from .vector_store import CaptionVectorStore

logger = logging.getLogger(__name__)

CTA_LABELS = {1: "comment bait", 2: "DM me", 3: "link in bio"}


def caption_document(
    caption: str,
    *,
    pillar: str = "",
    post_format: str = "",
    hashtags: list[str] | None = None,
) -> str:
    tags = ", ".join(hashtags or [])
    return (
        f"pillar={pillar}\n"
        f"format={post_format}\n"
        f"hashtags={tags}\n"
        f"caption={caption.strip()}"
    )


def build_caption_query(context: str, *, cta: int) -> str:
    return (
        "Instagram caption for @itslorenamor in Lorena's voice.\n"
        f"Post context: {context.strip()}\n"
        f"CTA style: {CTA_LABELS.get(cta, 'comment bait')}.\n"
        "Short, sassy, authentic UGC tone."
    )


def _pillar_for_assets(asset_ids: list[str]) -> str:
    if not asset_ids:
        return ""
    manifest = GalleryStore().load()
    by_id = {a.id: a for a in manifest.assets}
    pillars = {by_id[aid].pillar for aid in asset_ids if aid in by_id}
    if len(pillars) == 1:
        return next(iter(pillars))
    return pillars.pop() if pillars else ""


async def sync_caption_index() -> tuple[int, list[str]]:
    """Embed posted queue captions for style retrieval. Returns (updated_count, warnings)."""
    settings = get_settings()
    if not settings.rag_enabled:
        return 0, []

    store = CaptionVectorStore()
    client = get_embedding_client()
    warnings: list[str] = []
    posted = GalleryQueueStore().list_posted()

    keep_ids: set[str] = set()
    to_embed: list[tuple[str, str, str, str]] = []

    for item in posted:
        caption_id = item["item_id"]
        caption = (item.get("caption") or "").strip()
        if not caption:
            continue
        keep_ids.add(caption_id)
        pillar = _pillar_for_assets(item.get("asset_ids") or [])
        post_format = item.get("format") or "reel"
        hashtags = item.get("hashtags") or []
        document = caption_document(
            caption,
            pillar=pillar,
            post_format=post_format,
            hashtags=hashtags,
        )
        digest = doc_hash(document)
        existing = store.get(caption_id)
        if existing is None or existing[0] != digest:
            to_embed.append((caption_id, document, caption, pillar))

    removed = store.delete_missing(keep_ids)
    if removed:
        warnings.append(f"rag_caption_index_removed_{removed}_stale")

    if not to_embed:
        return 0, warnings

    try:
        vectors = await client.embed([document for _, document, _, _ in to_embed])
    except Exception as exc:
        logger.warning("Caption index sync failed: %s", exc)
        warnings.append(f"rag_caption_index_sync_failed:{type(exc).__name__}")
        return 0, warnings

    for (caption_id, document, caption_text, pillar), vector in zip(to_embed, vectors):
        digest = doc_hash(document)
        store.upsert(
            caption_id,
            digest,
            caption_text,
            pillar=pillar,
            embedding=vector,
            search_text=document,
        )

    return len(to_embed), warnings


async def retrieve_caption_examples(
    context: str,
    *,
    cta: int = 1,
) -> tuple[list[str], list[str], list[RetrievalHit]]:
    """Return past posted captions similar to the requested context."""
    settings = get_settings()
    warnings: list[str] = []
    hits: list[RetrievalHit] = []

    if not settings.rag_enabled:
        return [], warnings, hits

    sync_count, sync_warnings = await sync_caption_index()
    warnings.extend(sync_warnings)
    if sync_count:
        warnings.append(f"rag_caption_index_synced_{sync_count}")

    store = CaptionVectorStore()
    if store.count() == 0:
        warnings.append("rag_caption_index_empty")
        return [], warnings, hits

    query = build_caption_query(context, cta=cta)
    try:
        client = get_embedding_client()
        query_vector = await client.embed_one(query)
    except Exception as exc:
        logger.warning("Caption retrieval query embed failed: %s", exc)
        warnings.append(f"rag_caption_query_embed_failed:{type(exc).__name__}")
        return [], warnings, hits

    top_k = settings.rag_caption_top_k
    ranked = store.search_hybrid(query_vector, query, top_k=top_k)
    examples = [text for _cid, _score, text, _pillar in ranked if text.strip()]
    hits = [
        RetrievalHit(
            id=caption_id,
            score=round(max(0.0, score), 4),
            pillar=pillar,
            kind="caption",
        )
        for caption_id, score, _text, pillar in ranked
    ]

    if examples:
        warnings.append(f"rag_caption_retrieved_{len(examples)}_examples")
        parts = [f"{hit.id}={hit.score:.3f}" for hit in hits]
        warnings.append(f"rag_caption_scores:{','.join(parts)}")

    return examples, warnings, hits
