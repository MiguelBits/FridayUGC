from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class GalleryVectorStore:
    """SQLite-backed embedding index for gallery assets."""

    def __init__(self, path: str | None = None) -> None:
        settings = get_settings()
        default = Path(__file__).resolve().parents[2] / "data" / "gallery" / "rag_index.db"
        self.path = Path(path or settings.rag_index_path or default)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gallery_embeddings (
                    asset_id TEXT PRIMARY KEY,
                    doc_hash TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gallery_index_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS caption_embeddings (
                    caption_id TEXT PRIMARY KEY,
                    doc_hash TEXT NOT NULL,
                    caption_text TEXT NOT NULL,
                    pillar TEXT NOT NULL DEFAULT '',
                    embedding TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def get(self, asset_id: str) -> tuple[str, list[float]] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT doc_hash, embedding FROM gallery_embeddings WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
        if row is None:
            return None
        return row["doc_hash"], json.loads(row["embedding"])

    def upsert(self, asset_id: str, doc_hash: str, embedding: list[float]) -> None:
        payload = json.dumps(embedding)
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO gallery_embeddings (asset_id, doc_hash, embedding, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    doc_hash = excluded.doc_hash,
                    embedding = excluded.embedding,
                    updated_at = excluded.updated_at
                """,
                (asset_id, doc_hash, payload, now),
            )

    def delete_missing(self, keep_ids: set[str]) -> int:
        with self._conn() as conn:
            rows = conn.execute("SELECT asset_id FROM gallery_embeddings").fetchall()
            stale = [row["asset_id"] for row in rows if row["asset_id"] not in keep_ids]
            for asset_id in stale:
                conn.execute("DELETE FROM gallery_embeddings WHERE asset_id = ?", (asset_id,))
        return len(stale)

    def all_embeddings(self) -> dict[str, list[float]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT asset_id, embedding FROM gallery_embeddings").fetchall()
        return {row["asset_id"]: json.loads(row["embedding"]) for row in rows}

    def search(self, query_vector: list[float], *, top_k: int) -> list[tuple[str, float]]:
        scored: list[tuple[str, float]] = []
        for asset_id, vector in self.all_embeddings().items():
            scored.append((asset_id, cosine_similarity(query_vector, vector)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM gallery_embeddings").fetchone()
        return int(row["n"]) if row else 0

    def set_meta(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO gallery_index_meta (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_meta(self, key: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM gallery_index_meta WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row else None


class CaptionVectorStore:
    """SQLite-backed embedding index for posted caption examples."""

    def __init__(self, path: str | None = None) -> None:
        # Shares rag_index.db with gallery embeddings.
        self._gallery = GalleryVectorStore(path)
        self.path = self._gallery.path

    def get(self, caption_id: str) -> tuple[str, list[float], str] | None:
        with self._gallery._conn() as conn:
            row = conn.execute(
                "SELECT doc_hash, embedding, caption_text FROM caption_embeddings WHERE caption_id = ?",
                (caption_id,),
            ).fetchone()
        if row is None:
            return None
        return row["doc_hash"], json.loads(row["embedding"]), row["caption_text"]

    def upsert(
        self,
        caption_id: str,
        doc_hash: str,
        caption_text: str,
        *,
        pillar: str,
        embedding: list[float],
    ) -> None:
        payload = json.dumps(embedding)
        now = _utc_now()
        with self._gallery._conn() as conn:
            conn.execute(
                """
                INSERT INTO caption_embeddings (
                    caption_id, doc_hash, caption_text, pillar, embedding, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(caption_id) DO UPDATE SET
                    doc_hash = excluded.doc_hash,
                    caption_text = excluded.caption_text,
                    pillar = excluded.pillar,
                    embedding = excluded.embedding,
                    updated_at = excluded.updated_at
                """,
                (caption_id, doc_hash, caption_text, pillar, payload, now),
            )

    def delete_missing(self, keep_ids: set[str]) -> int:
        with self._gallery._conn() as conn:
            rows = conn.execute("SELECT caption_id FROM caption_embeddings").fetchall()
            stale = [row["caption_id"] for row in rows if row["caption_id"] not in keep_ids]
            for caption_id in stale:
                conn.execute("DELETE FROM caption_embeddings WHERE caption_id = ?", (caption_id,))
        return len(stale)

    def all_embeddings(self) -> dict[str, tuple[list[float], str, str]]:
        with self._gallery._conn() as conn:
            rows = conn.execute(
                "SELECT caption_id, embedding, caption_text, pillar FROM caption_embeddings"
            ).fetchall()
        return {
            row["caption_id"]: (json.loads(row["embedding"]), row["caption_text"], row["pillar"])
            for row in rows
        }

    def search(self, query_vector: list[float], *, top_k: int) -> list[tuple[str, float, str, str]]:
        scored: list[tuple[str, float, str, str]] = []
        for caption_id, (vector, text, pillar) in self.all_embeddings().items():
            scored.append((caption_id, cosine_similarity(query_vector, vector), text, pillar))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def count(self) -> int:
        with self._gallery._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM caption_embeddings").fetchone()
        return int(row["n"]) if row else 0
