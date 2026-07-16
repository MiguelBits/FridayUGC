"""Post gallery queue items via instagrapi."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..gallery.queue import GalleryQueueStore
from ..gallery.store import GalleryStore
from .client import FridayInstagramClient, get_instagram_client

logger = logging.getLogger(__name__)


def _resolve_media_path(asset_id: str) -> Path:
    queue = GalleryQueueStore()
    with queue._conn() as conn:
        row = conn.execute(
            "SELECT media_path FROM asset_inventory WHERE asset_id = ?", (asset_id,)
        ).fetchone()
    if row and row["media_path"]:
        path = Path(row["media_path"])
        if path.is_file():
            return path

    manifest = GalleryStore().load()
    asset = next((a for a in manifest.assets if a.id == asset_id), None)
    if not asset:
        raise FileNotFoundError(f"Unknown asset {asset_id}")
    if asset.local_path:
        path = Path(asset.local_path)
        if path.is_file():
            return path
    root = Path(__file__).resolve().parents[2] / "data" / "gallery"
    for candidate in (root / asset_id, root / f"{asset_id}.mp4", root / f"{asset_id}.jpg"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No media file for asset {asset_id}")


def _build_caption(item: dict[str, Any]) -> str:
    tags = item.get("hashtags") or []
    tag_block = " ".join(f"#{t.lstrip('#')}" for t in tags if t)
    body = (item.get("caption") or "").strip()
    if tag_block:
        return f"{body}\n\n{tag_block}".strip()
    return body


def post_queue_item(
    item: dict[str, Any],
    *,
    ig: FridayInstagramClient | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Upload one queued item. Returns media pk + idempotency metadata."""
    ig = ig or get_instagram_client()
    settings = get_settings()
    asset_ids: list[str] = item["asset_ids"]
    if not asset_ids:
        raise ValueError("queue item has no assets")

    media_path = _resolve_media_path(asset_ids[0])
    caption = _build_caption(item)
    fmt = (item.get("format") or "reel").lower()
    idem = item.get("idempotency_key") or f"post-{item['item_id']}"

    if dry_run or settings.ig_read_only:
        logger.info("[dry-run] would post %s as %s: %s", media_path.name, fmt, caption[:80])
        return {"ok": True, "dry_run": True, "format": fmt, "path": str(media_path)}

    cl = ig.client()
    ig.human_pause(2.0, 5.0)

    if fmt in {"reel", "clip", "video"}:
        media = cl.clip_upload(media_path, caption)
    elif fmt in {"story", "stories"}:
        if media_path.suffix.lower() in {".mp4", ".mov", ".webm"}:
            media = cl.video_upload_to_story(media_path, caption)
        else:
            media = cl.photo_upload_to_story(media_path, caption)
    else:
        if media_path.suffix.lower() in {".mp4", ".mov", ".webm"}:
            media = cl.video_upload(media_path, caption)
        else:
            media = cl.photo_upload(media_path, caption)

    media_pk = str(getattr(media, "pk", media))
    GalleryQueueStore().mark_posted(
        item_id=item["item_id"],
        asset_ids=asset_ids,
        idempotency_key=idem,
    )
    logger.info("Posted %s as %s — media_pk=%s", media_path.name, fmt, media_pk)
    return {"ok": True, "media_pk": media_pk, "format": fmt, "idempotency_key": idem}


def post_due(*, limit: int = 1, dry_run: bool = False) -> list[dict[str, Any]]:
    """Post up to `limit` due gallery queue items."""
    queue = GalleryQueueStore()
    due = queue.list_due()[:limit]
    results: list[dict[str, Any]] = []
    ig = get_instagram_client()
    for item in due:
        try:
            results.append(post_queue_item(item, ig=ig, dry_run=dry_run))
        except Exception as exc:
            logger.exception("Failed to post item %s", item.get("item_id"))
            results.append({"ok": False, "item_id": item.get("item_id"), "error": str(exc)})
    return results
