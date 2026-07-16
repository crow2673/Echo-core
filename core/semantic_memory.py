#!/usr/bin/env python3
"""Persistent semantic memory for storing and retrieving Echo exchanges."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path.home() / "Echo/echo_semantic_memory.sqlite"
_model = None


def _conn():
    db = sqlite3.connect(str(DB_PATH), timeout=15)
    db.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            embedding BLOB NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL,
            retrieval_count INTEGER DEFAULT 0,
            last_retrieved TEXT,
            promotion_score REAL DEFAULT 0.0,
            outcome_score REAL DEFAULT 0.5
        )
    """)
    db.commit()
    return db


def _embed(text: str):
    global _model
    import numpy as np
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
    return np.asarray(
        _model.encode(text, normalize_embeddings=True),
        dtype=np.float32,
    )


def remember(text: str, metadata: dict | None = None) -> int | None:
    """Store one meaningful memory, deduplicating exact text."""
    text = str(text or "").strip()
    if len(text) < 20:
        return None
    db = _conn()
    existing = db.execute("SELECT id FROM memories WHERE text=? LIMIT 1", (text,)).fetchone()
    if existing:
        db.close()
        return existing[0]
    embedding = _embed(text).tobytes()
    cur = db.execute(
        "INSERT INTO memories (text, embedding, metadata, created_at) VALUES (?,?,?,?)",
        (
            text,
            embedding,
            json.dumps(metadata or {}),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db.commit()
    memory_id = cur.lastrowid
    db.close()
    return memory_id


def remember_exchange(user_text: str, echo_text: str, source: str) -> int | None:
    return remember(
        f"User: {str(user_text).strip()}\nEcho: {str(echo_text).strip()}",
        {"type": "exchange", "source": source},
    )


def recall(
    query: str,
    limit: int = 4,
    min_similarity: float = 0.45,
    exclude_exchanges: bool = False,
) -> list[dict]:
    """Return relevant memories and update retrieval counters."""
    import numpy as np

    query = str(query or "").strip()
    if not query:
        return []
    query_embedding = _embed(query)
    db = _conn()
    rows = db.execute(
        "SELECT id, text, embedding, metadata, promotion_score "
        "FROM memories ORDER BY id DESC LIMIT 10000"
    ).fetchall()
    matches = []
    for memory_id, text, blob, metadata, promotion_score in rows:
        parsed_metadata = json.loads(metadata or "{}")
        if not blob or "queued MESSAGE:" in text:
            continue
        if exclude_exchanges and parsed_metadata.get("type") == "exchange":
            continue
        embedding = np.frombuffer(blob, dtype=np.float32)
        if embedding.shape != query_embedding.shape:
            continue
        norm = float(np.linalg.norm(embedding))
        if not norm:
            continue
        similarity = float(np.dot(query_embedding, embedding / norm))
        if similarity < min_similarity:
            continue
        matches.append({
            "id": memory_id,
            "text": text,
            "metadata": parsed_metadata,
            "similarity": round(similarity, 4),
            "promotion_score": promotion_score or 0.0,
        })

    matches.sort(
        key=lambda item: item["similarity"] + min(item["promotion_score"], 1.0) * 0.05,
        reverse=True,
    )
    selected = matches[:limit]
    if selected:
        now = datetime.now(timezone.utc).isoformat()
        db.executemany(
            "UPDATE memories SET retrieval_count=retrieval_count+1, last_retrieved=? WHERE id=?",
            [(now, item["id"]) for item in selected],
        )
        db.commit()
    db.close()
    return selected


def context_block(query: str, limit: int = 4) -> str:
    try:
        from core.structured_facts import format_fact_for_context, retrieve_preferred_fact
        preferred = retrieve_preferred_fact(query)
        if preferred:
            return (
                "REVIEWED STRUCTURED FACTS (prefer these over raw memories when directly relevant):\n"
                + format_fact_for_context(preferred["fact"])
            )
    except Exception:
        pass

    self_model_terms = (
        "conscious", "self-aware", "self aware", "confidence", "regret",
        "what are you", "your limits", "your capabilities", "yourself",
    )
    exclude_exchanges = any(term in query.lower() for term in self_model_terms)
    memories = recall(query, limit=limit, exclude_exchanges=exclude_exchanges)
    if not memories:
        return ""
    snippets = [m["text"][:700] for m in memories]
    return (
        "RELEVANT LONG-TERM MEMORIES (historical evidence; may be outdated or wrong):\n"
        + "\n\n".join(snippets)
    )


def retrieve_with_provenance(query: str, limit: int = 4) -> dict:
    """Return the preferred memory source with provenance.

    Reviewed structured facts win. If none match, this falls back to the
    existing semantic-memory recall path.
    """
    try:
        from core.structured_facts import retrieve_preferred_fact
        preferred = retrieve_preferred_fact(query)
        if preferred:
            return {
                "source": "structured_current_fact",
                "status": "current",
                "confidence": preferred["fact"].get("confidence"),
                "privacy_scope": preferred["fact"].get("privacy_scope"),
                "fact": preferred["fact"],
                "provenance": preferred["provenance"],
            }
    except Exception:
        pass

    memories = recall(query, limit=limit)
    if memories:
        return {
            "source": "semantic_raw_memory",
            "status": "unreviewed_raw_evidence",
            "confidence": None,
            "privacy_scope": "unknown",
            "memories": memories,
            "provenance": {
                "source_type": "semantic_memory",
                "memory_ids": [item["id"] for item in memories],
            },
        }
    return {
        "source": "none",
        "status": "unverified",
        "confidence": None,
        "privacy_scope": "unknown",
        "memories": [],
        "provenance": {"source_type": "none"},
    }
