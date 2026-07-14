from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import get_settings
from .schemas import GalleryAsset
from .store import GalleryStore


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GalleryQueueStore:
    """Persisted curation queue with scheduled posts for phone sync."""

    def __init__(self, path: str | None = None) -> None:
        settings = get_settings()
        default = Path(__file__).resolve().parents[2] / "data" / "gallery" / "queue.db"
        self.path = Path(path or settings.gallery_queue_path or default)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS queue_items (
                    item_id TEXT PRIMARY KEY,
                    asset_ids TEXT NOT NULL,
                    format TEXT NOT NULL,
                    caption TEXT NOT NULL,
                    hashtags TEXT NOT NULL,
                    location TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS asset_inventory (
                    asset_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    media_path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    vision_status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS post_receipts (
                    idempotency_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def scan_local_folder(self, folder: Path | None = None) -> list[dict[str, Any]]:
        store = GalleryStore()
        manifest = store.load()
        root = folder or (Path(store._local).parent if hasattr(store, "_local") else Path("data/gallery"))
        if not root.is_dir():
            root = Path(__file__).resolve().parents[2] / "data" / "gallery"
        found: list[dict[str, Any]] = []
        for asset in manifest.assets:
            path = Path(asset.local_path) if asset.local_path else root / asset.id
            if not path.is_file():
                for ext in (".mp4", ".mov", ".jpg", ".jpeg", ".png"):
                    candidate = root / f"{asset.id}{ext}"
                    if candidate.is_file():
                        path = candidate
                        break
            status = "ok" if path.is_file() else "missing"
            content_hash = ""
            if path.is_file():
                content_hash = hashlib.sha256(path.read_bytes()[:65536]).hexdigest()
            self.upsert_inventory(
                asset_id=asset.id,
                content_hash=content_hash,
                media_path=str(path) if path.is_file() else "",
                kind=asset.kind,
                metadata=asset.model_dump(),
                vision_status="analyzed" if asset.vision_summary else "pending",
            )
            found.append(
                {
                    "asset_id": asset.id,
                    "media_path": str(path) if path.is_file() else None,
                    "status": status,
                    "content_hash": content_hash,
                }
            )
        return found

    def upsert_inventory(
        self,
        *,
        asset_id: str,
        content_hash: str,
        media_path: str,
        kind: str,
        metadata: dict[str, Any],
        vision_status: str,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO asset_inventory(asset_id, content_hash, media_path, kind, metadata, vision_status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    media_path = excluded.media_path,
                    kind = excluded.kind,
                    metadata = excluded.metadata,
                    vision_status = excluded.vision_status,
                    updated_at = excluded.updated_at
                """,
                (asset_id, content_hash, media_path, kind, json.dumps(metadata), vision_status, _utc_now()),
            )

    def enqueue_from_assets(
        self,
        assets: list[GalleryAsset],
        *,
        format: str,
        caption: str,
        hashtags: list[str],
        location: str = "",
        scheduled_at: str,
        timezone: str = "America/New_York",
    ) -> dict[str, Any]:
        missing = [a.id for a in assets if not self._asset_exists(a.id)]
        if missing:
            raise ValueError(f"Missing or broken assets: {missing}")
        item_id = str(uuid.uuid4())
        idem = hashlib.sha256(f"{format}:{','.join(a.id for a in assets)}:{scheduled_at}".encode()).hexdigest()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO queue_items(
                    item_id, asset_ids, format, caption, hashtags, location,
                    scheduled_at, timezone, status, retry_count, idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
                """,
                (
                    item_id,
                    json.dumps([a.id for a in assets]),
                    format,
                    caption,
                    json.dumps(hashtags),
                    location,
                    scheduled_at,
                    timezone,
                    idem,
                    _utc_now(),
                ),
            )
        return self.get_item(item_id)

    def _asset_exists(self, asset_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT media_path FROM asset_inventory WHERE asset_id = ?", (asset_id,)
            ).fetchone()
        if row and row["media_path"]:
            return True
        # Dev fallback: manifest entry is enough when local media file is absent.
        manifest = GalleryStore().load()
        return any(a.id == asset_id for a in manifest.assets)

    def list_due(self, before: str | None = None) -> list[dict[str, Any]]:
        before = before or _utc_now()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM queue_items WHERE status = 'pending' AND scheduled_at <= ? ORDER BY scheduled_at",
                (before,),
            ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def list_all(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM queue_items ORDER BY scheduled_at").fetchall()
        return [self._row_to_item(r) for r in rows]

    def list_posted(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM queue_items WHERE status = 'posted' ORDER BY scheduled_at DESC"
            ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get_item(self, item_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM queue_items WHERE item_id = ?", (item_id,)).fetchone()
        if not row:
            raise KeyError(item_id)
        return self._row_to_item(row)

    def mark_posted(self, *, item_id: str | None, asset_ids: list[str], idempotency_key: str) -> dict[str, Any]:
        cached = self._get_post_receipt(idempotency_key)
        if cached:
            return cached
        store = GalleryStore()
        store.mark_posted(asset_ids)
        with self._conn() as conn:
            if item_id:
                conn.execute(
                    "UPDATE queue_items SET status = 'posted' WHERE item_id = ?",
                    (item_id,),
                )
            else:
                for aid in asset_ids:
                    conn.execute(
                        "UPDATE queue_items SET status = 'posted' WHERE asset_ids LIKE ?",
                        (f'%"{aid}"%',),
                    )
            payload = {"ok": True, "asset_ids": asset_ids, "idempotency_key": idempotency_key}
            conn.execute(
                "INSERT OR IGNORE INTO post_receipts(idempotency_key, payload, created_at) VALUES (?, ?, ?)",
                (idempotency_key, json.dumps(payload), _utc_now()),
            )
        return payload

    def _get_post_receipt(self, key: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload FROM post_receipts WHERE idempotency_key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        data = json.loads(row["payload"])
        data["deduplicated"] = True
        return data

    def _put_post_receipt(self, key: str, payload: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO post_receipts(idempotency_key, payload, created_at) VALUES (?, ?, ?)",
                (key, json.dumps(payload), _utc_now()),
            )

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "item_id": row["item_id"],
            "asset_ids": json.loads(row["asset_ids"]),
            "format": row["format"],
            "caption": row["caption"],
            "hashtags": json.loads(row["hashtags"]),
            "location": row["location"],
            "scheduled_at": row["scheduled_at"],
            "timezone": row["timezone"],
            "status": row["status"],
            "retry_count": row["retry_count"],
            "idempotency_key": row["idempotency_key"],
        }
