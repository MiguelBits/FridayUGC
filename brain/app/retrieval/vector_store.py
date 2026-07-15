from __future__ import annotations

import json
import math
import re
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


def _fts_query(text: str) -> str:
    """Build a safe FTS5 OR query from free text."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    tokens = [t for t in tokens if len(t) > 2][:16]
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens)


def _rrf_fuse(
    ranked_lists: list[list[tuple[str, float]]],
    *,
    top_k: int,
    k: int = 60,
) -> list[tuple[str, float]]:
    """Reciprocal rank fusion across ranked id lists."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (item_id, _raw) in enumerate(ranked):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)
    fused = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return fused[:top_k]


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
                    search_text TEXT NOT NULL DEFAULT '',
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
                CREATE VIRTUAL TABLE IF NOT EXISTS gallery_fts USING fts5(
                    asset_id UNINDEXED,
                    content,
                    tokenize='porter unicode61'
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS caption_fts USING fts5(
                    caption_id UNINDEXED,
                    content,
                    tokenize='porter unicode61'
                );
                """
            )
            self._ensure_search_text_column(conn)
            self._migrate_fts(conn)

    def _ensure_search_text_column(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(gallery_embeddings)").fetchall()}
        if "search_text" not in cols:
            conn.execute(
                "ALTER TABLE gallery_embeddings ADD COLUMN search_text TEXT NOT NULL DEFAULT ''"
            )

    def _migrate_fts(self, conn: sqlite3.Connection) -> None:
        """Backfill FTS rows for indexes created before hybrid search."""
        rows = conn.execute(
            "SELECT asset_id, search_text FROM gallery_embeddings WHERE search_text != ''"
        ).fetchall()
        for row in rows:
            conn.execute("DELETE FROM gallery_fts WHERE asset_id = ?", (row["asset_id"],))
            conn.execute(
                "INSERT INTO gallery_fts(asset_id, content) VALUES (?, ?)",
                (row["asset_id"], row["search_text"]),
            )
        cap_rows = conn.execute(
            "SELECT caption_id, caption_text FROM caption_embeddings WHERE caption_text != ''"
        ).fetchall()
        for row in cap_rows:
            conn.execute("DELETE FROM caption_fts WHERE caption_id = ?", (row["caption_id"],))
            conn.execute(
                "INSERT INTO caption_fts(caption_id, content) VALUES (?, ?)",
                (row["caption_id"], row["caption_text"]),
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

    def upsert(
        self,
        asset_id: str,
        doc_hash: str,
        embedding: list[float],
        *,
        search_text: str = "",
    ) -> None:
        payload = json.dumps(embedding)
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO gallery_embeddings (asset_id, doc_hash, search_text, embedding, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    doc_hash = excluded.doc_hash,
                    search_text = excluded.search_text,
                    embedding = excluded.embedding,
                    updated_at = excluded.updated_at
                """,
                (asset_id, doc_hash, search_text, payload, now),
            )
            if search_text.strip():
                conn.execute("DELETE FROM gallery_fts WHERE asset_id = ?", (asset_id,))
                conn.execute(
                    "INSERT INTO gallery_fts(asset_id, content) VALUES (?, ?)",
                    (asset_id, search_text),
                )

    def delete_missing(self, keep_ids: set[str]) -> int:
        with self._conn() as conn:
            rows = conn.execute("SELECT asset_id FROM gallery_embeddings").fetchall()
            stale = [row["asset_id"] for row in rows if row["asset_id"] not in keep_ids]
            for asset_id in stale:
                conn.execute("DELETE FROM gallery_embeddings WHERE asset_id = ?", (asset_id,))
                conn.execute("DELETE FROM gallery_fts WHERE asset_id = ?", (asset_id,))
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

    def search_lexical(self, query_text: str, *, top_k: int) -> list[tuple[str, float]]:
        fts_q = _fts_query(query_text)
        if not fts_q:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT asset_id, bm25(gallery_fts) AS rank
                FROM gallery_fts
                WHERE gallery_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_q, top_k),
            ).fetchall()
        # bm25 is negative — invert so higher is better for fusion.
        return [(row["asset_id"], -float(row["rank"])) for row in rows]

    def search_hybrid(
        self,
        query_vector: list[float],
        query_text: str,
        *,
        top_k: int,
    ) -> list[tuple[str, float]]:
        settings = get_settings()
        if not settings.rag_hybrid_enabled:
            return self.search(query_vector, top_k=top_k)

        vector_ranked = self.search(query_vector, top_k=max(top_k, top_k * 3))
        lexical_ranked = self.search_lexical(query_text, top_k=max(top_k, top_k * 3))
        if not lexical_ranked:
            return vector_ranked[:top_k]

        alpha = min(1.0, max(0.0, settings.rag_hybrid_alpha))
        if alpha >= 0.999:
            return vector_ranked[:top_k]
        if alpha <= 0.001:
            return lexical_ranked[:top_k]

        # Weighted RRF — vector list first when alpha is high.
        fused = _rrf_fuse(
            [vector_ranked, lexical_ranked],
            top_k=top_k,
        )
        if alpha > 0.5:
            return fused
        # Lexical-first tie-break when keyword weight dominates.
        return _rrf_fuse([lexical_ranked, vector_ranked], top_k=top_k)

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
        search_text: str = "",
    ) -> None:
        payload = json.dumps(embedding)
        now = _utc_now()
        fts_body = search_text.strip() or caption_text
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
            conn.execute("DELETE FROM caption_fts WHERE caption_id = ?", (caption_id,))
            conn.execute(
                "INSERT INTO caption_fts(caption_id, content) VALUES (?, ?)",
                (caption_id, fts_body),
            )

    def delete_missing(self, keep_ids: set[str]) -> int:
        with self._gallery._conn() as conn:
            rows = conn.execute("SELECT caption_id FROM caption_embeddings").fetchall()
            stale = [row["caption_id"] for row in rows if row["caption_id"] not in keep_ids]
            for caption_id in stale:
                conn.execute("DELETE FROM caption_embeddings WHERE caption_id = ?", (caption_id,))
                conn.execute("DELETE FROM caption_fts WHERE caption_id = ?", (caption_id,))
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

    def search_lexical(self, query_text: str, *, top_k: int) -> list[tuple[str, float, str, str]]:
        fts_q = _fts_query(query_text)
        if not fts_q:
            return []
        with self._gallery._conn() as conn:
            rows = conn.execute(
                """
                SELECT c.caption_id, c.caption_text, c.pillar, bm25(caption_fts) AS rank
                FROM caption_fts
                JOIN caption_embeddings c ON c.caption_id = caption_fts.caption_id
                WHERE caption_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_q, top_k),
            ).fetchall()
        return [
            (row["caption_id"], -float(row["rank"]), row["caption_text"], row["pillar"])
            for row in rows
        ]

    def search_hybrid(
        self,
        query_vector: list[float],
        query_text: str,
        *,
        top_k: int,
    ) -> list[tuple[str, float, str, str]]:
        settings = get_settings()
        if not settings.rag_hybrid_enabled:
            return self.search(query_vector, top_k=top_k)

        vector_ranked = self.search(query_vector, top_k=max(top_k, top_k * 3))
        lexical_ranked = self.search_lexical(query_text, top_k=max(top_k, top_k * 3))
        if not lexical_ranked:
            return vector_ranked[:top_k]

        alpha = min(1.0, max(0.0, settings.rag_hybrid_alpha))
        vec_ids = [(cid, score) for cid, score, _text, _pillar in vector_ranked]
        lex_ids = [(cid, score) for cid, score, _text, _pillar in lexical_ranked]
        if alpha >= 0.999:
            fused_ids = vec_ids[:top_k]
        elif alpha <= 0.001:
            fused_ids = lex_ids[:top_k]
        else:
            lists = [vec_ids, lex_ids] if alpha > 0.5 else [lex_ids, vec_ids]
            fused_ids = _rrf_fuse(lists, top_k=top_k)

        by_id = {cid: (score, text, pillar) for cid, score, text, pillar in vector_ranked}
        for cid, score, text, pillar in lexical_ranked:
            by_id.setdefault(cid, (score, text, pillar))

        out: list[tuple[str, float, str, str]] = []
        for cid, fused_score in fused_ids:
            score, text, pillar = by_id.get(cid, (fused_score, "", ""))
            out.append((cid, fused_score if fused_score else score, text, pillar))
        return out[:top_k]

    def count(self) -> int:
        with self._gallery._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM caption_embeddings").fetchone()
        return int(row["n"]) if row else 0
