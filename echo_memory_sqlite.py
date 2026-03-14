#!/usr/bin/env python3
"""
echo_memory_sqlite.py
=====================
Echo's semantic memory layer.
Harvested from Crungus/memory_sqlite.py, extended for Echo.

Stores exchanges as embeddings in SQLite.
Supports cosine similarity search for context retrieval.
"""

import sqlite3
import json
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from sentence_transformers import SentenceTransformer

DB_PATH = Path("/home/andrew/Echo/echo_semantic_memory.sqlite")
MODEL_NAME = "all-MiniLM-L6-v2"


class EchoMemory:
    def __init__(self, db_path: Path = DB_PATH):
        self.db = sqlite3.connect(str(db_path))
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                text            TEXT NOT NULL,
                embedding       BLOB NOT NULL,
                metadata        TEXT,
                created_at      TEXT,
                retrieval_count INTEGER DEFAULT 0,
                promotion_score REAL DEFAULT 0.5,
                last_retrieved  TEXT
            )
        """)
        # Migrate existing db — add columns if missing
        for col, defval in [
            ("retrieval_count", "0"),
            ("promotion_score", "0.5"),
            ("last_retrieved", "NULL"),
        ]:
            try:
                self.db.execute(f"ALTER TABLE memories ADD COLUMN {col} {'INTEGER' if col == 'retrieval_count' else 'REAL' if col == 'promotion_score' else 'TEXT'} DEFAULT {defval}")
                self.db.commit()
            except Exception:
                pass  # column already exists
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at    TEXT,
                summary       TEXT,
                capsule_count INTEGER
            )
        """)
        self.db.commit()
        self._encoder = None  # lazy load

    @property
    def encoder(self):
        if self._encoder is None:
            self._encoder = SentenceTransformer(MODEL_NAME)
        return self._encoder

    def _embed(self, text: str) -> np.ndarray:
        return self.encoder.encode([text])[0].astype("float32")

    def add(self, text: str, metadata: dict | None = None) -> int:
        vec = self._embed(text)
        meta_json = json.dumps(metadata or {})
        now = datetime.now(timezone.utc).isoformat()
        cur = self.db.execute(
            "INSERT INTO memories (text, embedding, metadata, created_at) VALUES (?, ?, ?, ?)",
            (text, vec.tobytes(), meta_json, now)
        )
        self.db.commit()
        return cur.lastrowid

    def search(self, query: str, k: int = 5) -> list[tuple[str, dict, float]]:
        """
        Returns list of (text, metadata, score) sorted by relevance descending.
        Blends cosine similarity (70%) with promotion score (30%).
        Updates retrieval_count and last_retrieved for returned memories.
        """
        q_vec = self._embed(query)
        rows = self.db.execute(
            "SELECT id, text, embedding, metadata, promotion_score FROM memories"
        ).fetchall()

        scored = []
        for row_id, text, emb_blob, meta_json, promo_score in rows:
            emb = np.frombuffer(emb_blob, dtype=np.float32)
            denom = np.linalg.norm(q_vec) * np.linalg.norm(emb)
            if denom == 0:
                continue
            cosine = float(np.dot(q_vec, emb) / denom)
            promo = float(promo_score or 0.5)
            # Blend: 70% similarity, 30% promotion with recency decay
            # Recency decay: memories not retrieved in 30+ days score lower
            import math
            decay = 1.0
            try:
                row_created = row[4] if len(row) > 4 else None
                # Use last_retrieved if available, else created_at
                last_used = None
                if len(row) > 6 and row[6]:
                    last_used = row[6]
                elif len(row) > 3 and row[3]:
                    meta = json.loads(row[3] or "{}")
                    last_used = meta.get("created_at")
                if last_used:
                    try:
                        last_dt = datetime.fromisoformat(last_used.replace("Z", "+00:00"))
                        days_old = (datetime.now(timezone.utc) - last_dt).days
                        decay = math.exp(-days_old / 60)  # half-life ~42 days
                    except Exception:
                        decay = 1.0
            except Exception:
                decay = 1.0
            blended = (cosine * 0.7) + (promo * decay * 0.3)
            scored.append((blended, row_id, text, json.loads(meta_json)))

        scored.sort(reverse=True, key=lambda x: x[0])
        top = scored[:k]

        # Update retrieval stats for returned memories
        now = datetime.now(timezone.utc).isoformat()
        for _, row_id, _, _ in top:
            self.db.execute(
                "UPDATE memories SET retrieval_count = retrieval_count + 1, last_retrieved = ? WHERE id = ?",
                (now, row_id)
            )
        self.db.commit()

        return [(t, m, s) for s, _, t, m in top]

    def promote(self, memory_id: int, delta: float = 0.1):
        """Increase promotion score — called when a memory informed a successful action."""
        self.db.execute(
            "UPDATE memories SET promotion_score = MIN(1.0, promotion_score + ?) WHERE id = ?",
            (delta, memory_id)
        )
        self.db.commit()

    def demote(self, memory_id: int, delta: float = 0.1):
        """Decrease promotion score — called when a memory informed a failed action."""
        self.db.execute(
            "UPDATE memories SET promotion_score = MAX(0.0, promotion_score - ?) WHERE id = ?",
            (delta, memory_id)
        )
        self.db.commit()

    def prune_low_value(self, threshold: float = 0.1, min_age_days: int = 30):
        """Remove memories that are never retrieved and have low promotion scores."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=min_age_days)).isoformat()
        cur = self.db.execute(
            "DELETE FROM memories WHERE promotion_score < ? AND (last_retrieved IS NULL OR last_retrieved < ?) AND retrieval_count = 0",
            (threshold, cutoff)
        )
        self.db.commit()
        return cur.rowcount

    def store_exchange(self, user_text: str, reply_text: str, capsule_id: str = ""):
        """Store a full user↔Echo exchange as a single memory entry."""
        combined = f"User: {user_text}\nEcho: {reply_text}"
        self.add(combined, metadata={
            "type": "exchange",
            "capsule_id": capsule_id,
        })

    def save_session_summary(self, summary: str, capsule_count: int):
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT INTO sessions (created_at, summary, capsule_count) VALUES (?, ?, ?)",
            (now, summary, capsule_count)
        )
        self.db.commit()

    def get_last_session_summary(self) -> dict | None:
        row = self.db.execute(
            "SELECT created_at, summary, capsule_count FROM sessions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return {"created_at": row[0], "summary": row[1], "capsule_count": row[2]}

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def close(self):
        self.db.close()


# --- module-level singleton for daemon use ---
_instance: EchoMemory | None = None

def get_memory() -> EchoMemory:
    global _instance
    if _instance is None:
        _instance = EchoMemory()
    return _instance


def build_memory_context(query: str, k: int = 5) -> str:
    """
    Search memory and return a formatted context block
    ready to inject into a system prompt.
    Returns empty string if no memories exist.
    """
    mem = get_memory()
    if mem.count() == 0:
        return ""

    results = mem.search(query, k=k)
    if not results:
        return ""

    lines = ["Relevant context from past sessions:"]
    for text, _, score in results:
        if score < 0.15:  # skip low-relevance noise
            continue
        lines.append(f"- {text}")

    if len(lines) == 1:  # only header, nothing passed threshold
        return ""

    return "\n".join(lines)


if __name__ == "__main__":
    # Quick smoke test
    mem = EchoMemory(db_path=Path("/tmp/echo_test_memory.sqlite"))
    mem.add("Echo is running on Andrew's Ubuntu machine with a Ryzen 9 5900X.")
    mem.add("Golem provider is configured on polygon mainnet with zero earnings so far.")
    mem.add("The Crungus memory system uses all-MiniLM-L6-v2 embeddings.")
    results = mem.search("what hardware is Echo running on?")
    print("Search results:")
    for text, meta, score in results:
        print(f"  [{score:.3f}] {text[:80]}")
    print("OK")
