from __future__ import annotations

import json
from datetime import datetime, timezone

from ..config import get_settings
from ..llm import ChatMessage, get_vision_llm
from ..persona import get_persona
from ..retrieval.gallery import sync_gallery_index
from .media import media_to_vision_b64
from .schemas import AnalyzeGalleryRequest, AnalyzeGalleryResponse, GalleryAsset, VisionAnalysis
from .store import GalleryStore

_VISION_SYSTEM = (
    "You are the visual director for @itslorenamor Instagram UGC. You SEE gallery frames and "
    "describe vibe, pairing potential, and content strategy. Identity anchor: pale green eyes, "
    "long black wavy hair, warm tan skin. Flag if eyes/hair seem wrong. SFW lifestyle/fitness only."
)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def _needs_vision(asset: GalleryAsset, force: bool) -> bool:
    if force:
        return True
    if not asset.vision_summary or not asset.vibe:
        return True
    return False


async def analyze_asset(
    asset: GalleryAsset,
    store: GalleryStore,
    *,
    force: bool = False,
    persona_key: str = "lorena",
) -> tuple[GalleryAsset, list[str]]:
    """Load the asset image/frame, run vision model, return enriched asset + warnings."""
    warnings: list[str] = []
    settings = get_settings()

    if not settings.vision_enabled:
        warnings.append(f"{asset.id}: vision_disabled")
        return asset, warnings

    if not _needs_vision(asset, force):
        return asset, warnings

    filename = asset.thumbnail_key or asset.s3_key or asset.local_path or asset.id
    raw = store.read_asset_bytes(asset)
    image_b64: str | None = None

    if raw:
        image_b64 = media_to_vision_b64(raw, filename, max_side=settings.vision_max_side_px)
        if not image_b64 and store.read_thumbnail_bytes(asset):
            thumb = store.read_thumbnail_bytes(asset)
            if thumb:
                image_b64 = media_to_vision_b64(thumb, "thumb.jpg", max_side=settings.vision_max_side_px)
    elif store.read_thumbnail_bytes(asset):
        thumb = store.read_thumbnail_bytes(asset)
        if thumb:
            image_b64 = media_to_vision_b64(thumb, "thumb.jpg", max_side=settings.vision_max_side_px)

    if not image_b64:
        warnings.append(f"{asset.id}: no_visual_frame")
        if get_settings().llm_provider.lower() != "mock":
            asset.vision_summary = asset.vision_summary or f"(text only) {asset.description}"
            asset.vibe = asset.vibe or asset.pillar
            asset.vision_analyzed_at = datetime.now(timezone.utc).isoformat()
            return asset, warnings

    persona = get_persona(persona_key)
    user = (
        "RETURN_VISION_JSON\n"
        "Study this gallery frame for @itslorenamor. Respond with JSON only:\n"
        "  vision_summary (2-3 sentences, what you SEE — outfit, setting, energy, lighting)\n"
        "  vibe (3-6 words, e.g. 'gritty leg day mirror')\n"
        "  pillar (gym|food|outfit|lifestyle|other)\n"
        "  visual_tags (list of 4-8 tags)\n"
        "  pairing_hints (list — what other content this groups with)\n"
        "  suggested_lane (A-E)\n"
        "  suggested_type (outfit try-on, workout exercise, food tutorial, silent, etc.)\n"
        "  on_screen_text_hint (ALL CAPS, <=8 words)\n"
        "  identity_ok (bool — pale green eyes consistent?)\n"
        "  warnings (list)\n\n"
        f"Asset id: {asset.id}\n"
        f"Human hint: {asset.description}\n"
        f"Kind: {asset.kind} | Tags: {asset.tags}"
    )

    llm = get_vision_llm()
    images = [image_b64] if image_b64 else []
    raw_json = await llm.chat(
        [
            ChatMessage("system", persona.system_prompt + "\n\n" + _VISION_SYSTEM),
            ChatMessage("user", user, images=images),
        ],
        json_mode=True,
        max_tokens=600,
    )

    data = _extract_json(raw_json)
    asset.vision_summary = str(data.get("vision_summary", asset.description))
    asset.vibe = str(data.get("vibe", asset.pillar))
    pillar_val = str(data.get("pillar", asset.pillar))
    if pillar_val in ("gym", "food", "outfit", "lifestyle", "silent", "other"):
        asset.pillar = pillar_val  # type: ignore[assignment]
    asset.visual_tags = [str(t) for t in data.get("visual_tags", [])][:10]
    asset.pairing_hints = [str(p) for p in data.get("pairing_hints", [])][:6]
    asset.suggested_lane = str(data.get("suggested_lane", "")) or None
    asset.suggested_type = str(data.get("suggested_type", "")) or None
    asset.on_screen_text_hint = str(data.get("on_screen_text_hint", "")).upper() or None
    asset.identity_ok = bool(data.get("identity_ok", True))
    asset.vision_analyzed_at = datetime.now(timezone.utc).isoformat()
    for w in data.get("warnings", []):
        warnings.append(f"{asset.id}: {w}")
    if not asset.identity_ok:
        warnings.append(f"{asset.id}: identity_drift_flagged")

    return asset, warnings


async def analyze_gallery(
    req: AnalyzeGalleryRequest,
    persona_key: str = "lorena",
) -> AnalyzeGalleryResponse:
    store = GalleryStore()
    manifest = store.load()
    targets = manifest.assets
    if req.asset_ids:
        ids = set(req.asset_ids)
        targets = [a for a in targets if a.id in ids]

    all_warnings: list[str] = []
    analyzed: list[VisionAnalysis] = []

    for i, asset in enumerate(targets):
        if not req.force and not _needs_vision(asset, False):
            analyzed.append(_to_vision_analysis(asset))
            continue
        enriched, warns = await analyze_asset(asset, store, force=req.force, persona_key=persona_key)
        for j, a in enumerate(manifest.assets):
            if a.id == enriched.id:
                manifest.assets[j] = enriched
                break
        all_warnings.extend(warns)
        analyzed.append(_to_vision_analysis(enriched))

    store.save(manifest)
    sync_count, sync_warnings = await sync_gallery_index(manifest.assets)
    if sync_count:
        all_warnings.append(f"rag_index_synced_{sync_count}_assets")
    all_warnings.extend(sync_warnings)
    return AnalyzeGalleryResponse(analyzed=len(analyzed), assets=analyzed, warnings=all_warnings)


async def ensure_vision(
    assets: list[GalleryAsset],
    store: GalleryStore,
    *,
    force: bool = False,
    persona_key: str = "lorena",
) -> tuple[list[GalleryAsset], list[str]]:
    """Analyze any assets missing vision data; persist updates to manifest."""
    if not get_settings().vision_enabled:
        return assets, ["vision_disabled"]

    manifest = store.load()
    by_id = {a.id: a for a in manifest.assets}
    warnings: list[str] = []
    enriched: list[GalleryAsset] = []

    for asset in assets:
        current = by_id.get(asset.id, asset)
        if not _needs_vision(current, force):
            enriched.append(current)
            continue
        updated, warns = await analyze_asset(current, store, force=force, persona_key=persona_key)
        by_id[updated.id] = updated
        warnings.extend(warns)
        enriched.append(updated)

    manifest.assets = [by_id.get(a.id, a) for a in manifest.assets]
    store.save(manifest)
    sync_count, sync_warnings = await sync_gallery_index(enriched)
    if sync_count:
        warnings.append(f"rag_index_synced_{sync_count}_assets")
    warnings.extend(sync_warnings)
    return enriched, warnings


def _to_vision_analysis(asset: GalleryAsset) -> VisionAnalysis:
    return VisionAnalysis(
        id=asset.id,
        vision_summary=asset.vision_summary or "",
        vibe=asset.vibe or "",
        pillar=asset.pillar,
        visual_tags=asset.visual_tags,
        pairing_hints=asset.pairing_hints,
        suggested_lane=asset.suggested_lane,
        suggested_type=asset.suggested_type,
        identity_ok=asset.identity_ok,
        vision_analyzed_at=asset.vision_analyzed_at,
    )
