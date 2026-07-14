from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta

from ..config import get_settings
from ..gallery.schemas import GalleryAsset, RetrievalHit
from .embeddings import get_embedding_client
from .vector_store import GalleryVectorStore

logger = logging.getLogger(__name__)

PILLAR_ROTATION = ["gym", "outfit", "food", "lifestyle", "gym", "outfit"]


def asset_document(asset: GalleryAsset) -> str:
    """Text blob indexed for semantic retrieval."""
    tags = ", ".join(asset.tags) if asset.tags else ""
    visual_tags = ", ".join(asset.visual_tags) if asset.visual_tags else ""
    pairing = ", ".join(asset.pairing_hints) if asset.pairing_hints else ""
    vision = asset.vision_summary or asset.description
    vibe = asset.vibe or ""
    return (
        f"id={asset.id}\n"
        f"pillar={asset.pillar}\n"
        f"kind={asset.kind}\n"
        f"vibe={vibe}\n"
        f"vision={vision}\n"
        f"description={asset.description}\n"
        f"tags={tags}\n"
        f"visual_tags={visual_tags}\n"
        f"pairing_hints={pairing}\n"
        f"suggested_lane={asset.suggested_lane or ''}\n"
        f"suggested_type={asset.suggested_type or ''}"
    )


def doc_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_curation_query(
    *,
    notes: str | None,
    days_ahead: int,
    max_posts_per_day: int,
) -> str:
    """Strategy query used to retrieve relevant gallery assets."""
    today = date.today()
    dates = [(today + timedelta(days=i)).isoformat() for i in range(days_ahead)]
    pillars = PILLAR_ROTATION[: min(days_ahead, len(PILLAR_ROTATION))]
    pillar_hint = ", ".join(pillars)
    return (
        "Weekly Instagram UGC plan for @itslorenamor.\n"
        f"Planning window: {days_ahead} days, up to {max_posts_per_day} posts/day.\n"
        f"Dates: {', '.join(dates)}.\n"
        f"Pillar rotation hint: {pillar_hint}.\n"
        "Mix gym, outfit, food, lifestyle. Group assets by vibe for carousels.\n"
        f"Director notes: {notes or 'balanced week across pillars'}"
    )


async def sync_gallery_index(assets: list[GalleryAsset]) -> tuple[int, list[str]]:
    """Embed gallery assets that changed since last index. Returns (updated_count, warnings)."""
    settings = get_settings()
    if not settings.rag_enabled:
        return 0, []

    store = GalleryVectorStore()
    client = get_embedding_client()
    warnings: list[str] = []
    to_embed: list[GalleryAsset] = []
    hashes: dict[str, str] = {}

    for asset in assets:
        document = asset_document(asset)
        digest = doc_hash(document)
        hashes[asset.id] = digest
        existing = store.get(asset.id)
        if existing is None or existing[0] != digest:
            to_embed.append(asset)

    removed = store.delete_missing(set(hashes))
    if removed:
        warnings.append(f"rag_index_removed_{removed}_stale_assets")

    if not to_embed:
        store.set_meta("last_sync_at", date.today().isoformat())
        return 0, warnings

    try:
        vectors = await client.embed([asset_document(asset) for asset in to_embed])
    except Exception as exc:
        logger.warning("Gallery index sync failed: %s", exc)
        warnings.append(f"rag_index_sync_failed:{type(exc).__name__}")
        return 0, warnings

    for asset, vector in zip(to_embed, vectors):
        store.upsert(asset.id, hashes[asset.id], vector)

    store.set_meta("last_sync_at", date.today().isoformat())
    store.set_meta("embedding_provider", settings.embedding_provider)
    return len(to_embed), warnings


def _format_score_warnings(hits: list[RetrievalHit]) -> list[str]:
    if not hits:
        return []
    parts = [f"{hit.id}={hit.score:.3f}" for hit in hits]
    return [f"rag_scores:{','.join(parts)}"]


def _hits_from_ranked(
    ranked: list[tuple[str, float]],
    by_id: dict[str, GalleryAsset],
) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    for asset_id, score in ranked:
        asset = by_id.get(asset_id)
        hits.append(
            RetrievalHit(
                id=asset_id,
                score=round(max(0.0, score), 4),
                pillar=asset.pillar if asset else "",
                kind="gallery",
            )
        )
    return hits


async def retrieve_assets_for_curation(
    assets: list[GalleryAsset],
    *,
    notes: str | None,
    days_ahead: int,
    max_posts_per_day: int,
) -> tuple[list[GalleryAsset], list[str], list[RetrievalHit]]:
    """Return the asset subset most relevant to the curation query."""
    settings = get_settings()
    warnings: list[str] = []
    hits: list[RetrievalHit] = []

    if not settings.rag_enabled:
        return assets, warnings, hits

    top_k = settings.rag_gallery_top_k
    if len(assets) <= top_k:
        sync_count, sync_warnings = await sync_gallery_index(assets)
        warnings.extend(sync_warnings)
        if sync_count:
            warnings.append(f"rag_index_synced_{sync_count}_assets")
        warnings.append(f"rag_skipped_small_gallery_{len(assets)}<={top_k}")
        return assets, warnings, hits

    sync_count, sync_warnings = await sync_gallery_index(assets)
    warnings.extend(sync_warnings)
    if sync_count:
        warnings.append(f"rag_index_synced_{sync_count}_assets")

    store = GalleryVectorStore()
    if store.count() == 0:
        warnings.append("rag_index_empty_fallback_all_assets")
        return assets, warnings, hits

    query = build_curation_query(
        notes=notes,
        days_ahead=days_ahead,
        max_posts_per_day=max_posts_per_day,
    )

    try:
        client = get_embedding_client()
        query_vector = await client.embed_one(query)
    except Exception as exc:
        logger.warning("Gallery retrieval query embed failed: %s", exc)
        warnings.append(f"rag_query_embed_failed:{type(exc).__name__}")
        return assets, warnings, hits

    ranked = store.search(query_vector, top_k=top_k)
    by_id = {asset.id: asset for asset in assets}
    selected_ids = {asset_id for asset_id, _score in ranked}
    selected = [by_id[asset_id] for asset_id, _score in ranked if asset_id in by_id]
    hits = _hits_from_ranked(ranked, by_id)

    # Keep pillar diversity when the gallery is large enough.
    seen_pillars = {asset.pillar for asset in selected}
    if len(selected) < top_k:
        for asset in assets:
            if asset.id in selected_ids:
                continue
            if asset.pillar not in seen_pillars:
                selected.append(asset)
                selected_ids.add(asset.id)
                seen_pillars.add(asset.pillar)
            if len(selected) >= top_k:
                break

    if not selected:
        warnings.append("rag_no_matches_fallback_all_assets")
        return assets, warnings, hits

    warnings.append(f"rag_retrieved_{len(selected)}_of_{len(assets)}_assets")
    warnings.extend(_format_score_warnings(hits))
    return selected, warnings, hits
