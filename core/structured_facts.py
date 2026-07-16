#!/usr/bin/env python3
"""Reviewed structured facts for Echo's personal/world memory.

This layer does not migrate or replace semantic memory. It records explicitly
reviewed facts, their lifecycle, and provenance so raw memories can remain raw.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE / "memory" / "structured_facts.sqlite"

STATUSES = {"candidate", "current", "stale", "superseded", "rejected", "unknown"}
PRIVACY_SCOPES = {"owner_private", "family_private", "shareable", "unknown"}
FACT_TYPES = {
    "item_location",
    "possession",
    "preference",
    "identity",
    "relationship",
    "permission",
    "configuration",
    "schedule",
    "general_fact",
}


class StructuredFactError(RuntimeError):
    pass


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _tokenize(value: str) -> set[str]:
    stop = {
        "the",
        "a",
        "an",
        "did",
        "do",
        "you",
        "where",
        "what",
        "with",
        "for",
        "are",
        "is",
        "my",
        "i",
        "those",
        "that",
        "this",
    }
    return {w for w in re.findall(r"[a-z0-9]+", normalize_text(value)) if len(w) > 2 and w not in stop}


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def make_fact_id(subject: str, predicate: str, normalized_value: str, source_reference: str = "") -> str:
    payload = "|".join([normalize_text(subject), normalize_text(predicate), normalize_text(normalized_value), source_reference])
    return "fact-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    ensure_schema(db)
    return db


def ensure_schema(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS structured_facts (
            fact_id TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object_value TEXT NOT NULL,
            object_type TEXT,
            relationship_context TEXT,
            normalized_value TEXT NOT NULL,
            fact_type TEXT NOT NULL,
            status TEXT NOT NULL,
            confidence REAL NOT NULL,
            privacy_scope TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_reference TEXT,
            source_memory_ids TEXT,
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by TEXT,
            last_verified_at TEXT,
            valid_from TEXT,
            valid_until TEXT,
            supersedes_fact_id TEXT,
            superseded_by_fact_id TEXT,
            stale_reason TEXT,
            notes TEXT,
            metadata TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS structured_fact_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            actor TEXT NOT NULL,
            reason TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            previous_state TEXT,
            resulting_state TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_structured_facts_subject_predicate ON structured_facts(subject, predicate)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_structured_facts_status ON structured_facts(status)")
    existing = [row[1] for row in db.execute("PRAGMA table_info(structured_facts)").fetchall()]
    if "object_type" not in existing:
        db.execute("ALTER TABLE structured_facts ADD COLUMN object_type TEXT")
    if "relationship_context" not in existing:
        db.execute("ALTER TABLE structured_facts ADD COLUMN relationship_context TEXT")
    db.commit()


def _validate_common(fact: dict[str, Any]) -> None:
    if fact.get("status") not in STATUSES:
        raise ValueError(f"unsupported status: {fact.get('status')}")
    if fact.get("privacy_scope") not in PRIVACY_SCOPES:
        raise ValueError(f"unsupported privacy_scope: {fact.get('privacy_scope')}")
    if fact.get("fact_type") not in FACT_TYPES:
        raise ValueError(f"unsupported fact_type: {fact.get('fact_type')}")
    confidence = float(fact.get("confidence", 0.0))
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")


def _row_to_fact(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    fact = dict(row)
    fact["source_memory_ids"] = _json_loads(fact.get("source_memory_ids"), [])
    fact["metadata"] = _json_loads(fact.get("metadata"), {})
    return fact


def _state_for_event(fact: dict[str, Any] | None) -> str | None:
    if fact is None:
        return None
    return _json_dumps(fact)


def _get_fact(db: sqlite3.Connection, fact_id: str) -> dict[str, Any] | None:
    return _row_to_fact(db.execute("SELECT * FROM structured_facts WHERE fact_id=?", (fact_id,)).fetchone())


def _write_event(
    db: sqlite3.Connection,
    fact_id: str,
    operation: str,
    actor: str,
    reason: str,
    previous: dict[str, Any] | None,
    resulting: dict[str, Any],
    timestamp: str | None = None,
) -> None:
    db.execute(
        """
        INSERT INTO structured_fact_events
        (fact_id, operation, actor, reason, timestamp, previous_state, resulting_state)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            fact_id,
            operation,
            actor,
            reason,
            timestamp or now_utc(),
            _state_for_event(previous),
            _state_for_event(resulting),
        ),
    )


def _insert_fact(db: sqlite3.Connection, fact: dict[str, Any]) -> None:
    db.execute(
        """
        INSERT INTO structured_facts (
            fact_id, subject, predicate, object_value, object_type, relationship_context,
            normalized_value, fact_type, status,
            confidence, privacy_scope, source_type, source_reference, source_memory_ids,
            created_at, reviewed_at, reviewed_by, last_verified_at, valid_from, valid_until,
            supersedes_fact_id, superseded_by_fact_id, stale_reason, notes, metadata, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            fact["fact_id"],
            fact["subject"],
            fact["predicate"],
            fact["object_value"],
            fact.get("object_type"),
            fact.get("relationship_context"),
            fact["normalized_value"],
            fact["fact_type"],
            fact["status"],
            float(fact["confidence"]),
            fact["privacy_scope"],
            fact["source_type"],
            fact.get("source_reference"),
            _json_dumps(fact.get("source_memory_ids", [])),
            fact["created_at"],
            fact.get("reviewed_at"),
            fact.get("reviewed_by"),
            fact.get("last_verified_at"),
            fact.get("valid_from"),
            fact.get("valid_until"),
            fact.get("supersedes_fact_id"),
            fact.get("superseded_by_fact_id"),
            fact.get("stale_reason"),
            fact.get("notes"),
            _json_dumps(fact.get("metadata", {})),
            fact["updated_at"],
        ),
    )


def _update_fact(db: sqlite3.Connection, fact: dict[str, Any]) -> None:
    db.execute(
        """
        UPDATE structured_facts SET
            subject=?, predicate=?, object_value=?, object_type=?, relationship_context=?,
            normalized_value=?, fact_type=?, status=?,
            confidence=?, privacy_scope=?, source_type=?, source_reference=?, source_memory_ids=?,
            reviewed_at=?, reviewed_by=?, last_verified_at=?, valid_from=?, valid_until=?,
            supersedes_fact_id=?, superseded_by_fact_id=?, stale_reason=?, notes=?, metadata=?,
            updated_at=?
        WHERE fact_id=?
        """,
        (
            fact["subject"],
            fact["predicate"],
            fact["object_value"],
            fact.get("object_type"),
            fact.get("relationship_context"),
            fact["normalized_value"],
            fact["fact_type"],
            fact["status"],
            float(fact["confidence"]),
            fact["privacy_scope"],
            fact["source_type"],
            fact.get("source_reference"),
            _json_dumps(fact.get("source_memory_ids", [])),
            fact.get("reviewed_at"),
            fact.get("reviewed_by"),
            fact.get("last_verified_at"),
            fact.get("valid_from"),
            fact.get("valid_until"),
            fact.get("supersedes_fact_id"),
            fact.get("superseded_by_fact_id"),
            fact.get("stale_reason"),
            fact.get("notes"),
            _json_dumps(fact.get("metadata", {})),
            fact["updated_at"],
            fact["fact_id"],
        ),
    )


def create_candidate(
    *,
    subject: str,
    predicate: str,
    object_value: str,
    object_type: str | None = None,
    relationship_context: str | None = None,
    fact_type: str,
    confidence: float,
    privacy_scope: str,
    source_type: str,
    source_reference: str = "",
    source_memory_ids: list[Any] | None = None,
    actor: str = "system",
    reason: str = "candidate created",
    notes: str = "",
    metadata: dict[str, Any] | None = None,
    valid_from: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    created = now_utc()
    normalized_value = normalize_text(object_value)
    fact_id = make_fact_id(subject, predicate, normalized_value, source_reference)
    fact = {
        "fact_id": fact_id,
        "subject": subject,
        "predicate": predicate,
        "object_value": object_value,
        "object_type": object_type,
        "relationship_context": relationship_context,
        "normalized_value": normalized_value,
        "fact_type": fact_type,
        "status": "candidate",
        "confidence": float(confidence),
        "privacy_scope": privacy_scope,
        "source_type": source_type,
        "source_reference": source_reference,
        "source_memory_ids": source_memory_ids or [],
        "created_at": created,
        "reviewed_at": None,
        "reviewed_by": None,
        "last_verified_at": None,
        "valid_from": valid_from,
        "valid_until": None,
        "supersedes_fact_id": None,
        "superseded_by_fact_id": None,
        "stale_reason": None,
        "notes": notes,
        "metadata": metadata or {},
        "updated_at": created,
    }
    _validate_common(fact)
    with connect(db_path) as db:
        existing = _get_fact(db, fact_id)
        if existing:
            return existing
        _insert_fact(db, fact)
        _write_event(db, fact_id, "create_candidate", actor, reason, None, fact, created)
        db.commit()
    return fact


def _active_current_conflict(db: sqlite3.Connection, fact: dict[str, Any]) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT * FROM structured_facts
        WHERE subject=? AND predicate=? AND status='current' AND fact_id<>?
        LIMIT 1
        """,
        (fact["subject"], fact["predicate"], fact["fact_id"]),
    ).fetchone()
    return _row_to_fact(row)


def approve_current(
    fact_id: str,
    *,
    reviewer: str,
    reason: str,
    last_verified_at: str | None = None,
    supersede_conflict: bool = False,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    ts = now_utc()
    with connect(db_path) as db:
        fact = _get_fact(db, fact_id)
        if not fact:
            raise StructuredFactError(f"fact not found: {fact_id}")
        if fact["status"] not in {"candidate", "current", "unknown"}:
            raise StructuredFactError(f"cannot approve fact in status {fact['status']}")
        conflict = _active_current_conflict(db, fact)
        previous = dict(fact)
        if conflict and not supersede_conflict:
            raise StructuredFactError(f"conflicting current fact exists: {conflict['fact_id']}")
        if conflict:
            conflict_previous = dict(conflict)
            conflict["status"] = "superseded"
            conflict["superseded_by_fact_id"] = fact_id
            conflict["updated_at"] = ts
            _update_fact(db, conflict)
            _write_event(db, conflict["fact_id"], "supersede", reviewer, reason, conflict_previous, conflict, ts)
            fact["supersedes_fact_id"] = conflict["fact_id"]
        fact["status"] = "current"
        fact["reviewed_at"] = ts
        fact["reviewed_by"] = reviewer
        fact["last_verified_at"] = last_verified_at or ts
        fact["updated_at"] = ts
        _update_fact(db, fact)
        _write_event(db, fact_id, "approve_current", reviewer, reason, previous, fact, ts)
        db.commit()
    return fact


def reject_candidate(fact_id: str, *, reviewer: str, reason: str, db_path: Path | str | None = None) -> dict[str, Any]:
    return _transition(
        fact_id,
        "rejected",
        "reject_candidate",
        reviewer,
        reason,
        set_review=True,
        db_path=db_path,
    )


def mark_stale(fact_id: str, *, actor: str, reason: str, db_path: Path | str | None = None) -> dict[str, Any]:
    return _transition(fact_id, "stale", "mark_stale", actor, reason, stale_reason=reason, db_path=db_path)


def verify_current(fact_id: str, *, actor: str, reason: str, db_path: Path | str | None = None) -> dict[str, Any]:
    ts = now_utc()
    with connect(db_path) as db:
        fact = _get_fact(db, fact_id)
        if not fact:
            raise StructuredFactError(f"fact not found: {fact_id}")
        if fact["status"] != "current":
            raise StructuredFactError("only current facts can be verified")
        previous = dict(fact)
        fact["last_verified_at"] = ts
        fact["updated_at"] = ts
        _update_fact(db, fact)
        _write_event(db, fact_id, "verify_current", actor, reason, previous, fact, ts)
        db.commit()
    return fact


def _transition(
    fact_id: str,
    status: str,
    operation: str,
    actor: str,
    reason: str,
    *,
    stale_reason: str | None = None,
    set_review: bool = False,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    ts = now_utc()
    with connect(db_path) as db:
        fact = _get_fact(db, fact_id)
        if not fact:
            raise StructuredFactError(f"fact not found: {fact_id}")
        previous = dict(fact)
        fact["status"] = status
        if stale_reason:
            fact["stale_reason"] = stale_reason
        if set_review:
            fact["reviewed_at"] = ts
            fact["reviewed_by"] = actor
        fact["updated_at"] = ts
        _update_fact(db, fact)
        _write_event(db, fact_id, operation, actor, reason, previous, fact, ts)
        db.commit()
    return fact


def supersede(
    old_fact_id: str,
    *,
    new_fact: dict[str, Any],
    reviewer: str,
    reason: str,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    created = create_candidate(**new_fact, actor=reviewer, reason=reason, db_path=db_path)
    return approve_current(
        created["fact_id"],
        reviewer=reviewer,
        reason=reason,
        supersede_conflict=True,
        db_path=db_path,
    )


def get_current_fact(
    subject: str,
    predicate: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    with connect(db_path) as db:
        row = db.execute(
            """
            SELECT * FROM structured_facts
            WHERE subject=? AND predicate=? AND status='current'
            ORDER BY last_verified_at DESC, reviewed_at DESC, created_at DESC
            LIMIT 1
            """,
            (subject, predicate),
        ).fetchone()
        return _row_to_fact(row)


def list_fact_history(subject: str, predicate: str, *, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as db:
        rows = db.execute(
            """
            SELECT * FROM structured_facts
            WHERE subject=? AND predicate=?
            ORDER BY created_at ASC
            """,
            (subject, predicate),
        ).fetchall()
        return [_row_to_fact(row) for row in rows]


def list_events(fact_id: str, *, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as db:
        rows = db.execute(
            """
            SELECT * FROM structured_fact_events
            WHERE fact_id=?
            ORDER BY event_id ASC
            """,
            (fact_id,),
        ).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            event["previous_state"] = _json_loads(event.get("previous_state"), None)
            event["resulting_state"] = _json_loads(event.get("resulting_state"), {})
            events.append(event)
        return events


def search_facts(
    query: str,
    *,
    status: str | None = None,
    limit: int = 5,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []
    with connect(db_path) as db:
        if status:
            rows = db.execute("SELECT * FROM structured_facts WHERE status=?", (status,)).fetchall()
        else:
            rows = db.execute("SELECT * FROM structured_facts").fetchall()
    ranked = []
    for row in rows:
        fact = _row_to_fact(row)
        raw_query_tokens = set(re.findall(r"[a-z0-9]+", normalize_text(query)))
        haystack = " ".join(
            [
                fact.get("subject", ""),
                fact.get("predicate", ""),
                fact.get("object_value", ""),
                fact.get("object_type", "") or "",
                fact.get("relationship_context", "") or "",
                fact.get("normalized_value", ""),
                fact.get("notes", "") or "",
            ]
        )
        tokens = _tokenize(haystack)
        overlap = query_tokens & tokens
        subject_overlap = query_tokens & _tokenize(fact.get("subject", ""))
        predicate_overlap = query_tokens & _tokenize(fact.get("predicate", ""))
        predicate_hint = any(word in raw_query_tokens for word in {"where", "location", "stored", "put"}) and fact.get("fact_type") == "item_location"
        if fact.get("fact_type") == "item_location" and not predicate_hint and not predicate_overlap:
            continue
        if not overlap and not predicate_hint:
            continue
        score = len(overlap) + (2 if subject_overlap else 0) + (1 if predicate_hint else 0)
        fact["match_score"] = score
        fact["match_terms"] = sorted(overlap)
        ranked.append(fact)
    ranked.sort(key=lambda item: (item["match_score"], item.get("last_verified_at") or "", item.get("created_at") or ""), reverse=True)
    return ranked[:limit]


def retrieve_preferred_fact(query: str, *, db_path: Path | str | None = None) -> dict[str, Any] | None:
    matches = search_facts(query, status="current", limit=1, db_path=db_path)
    if not matches:
        return None
    fact = matches[0]
    return {
        "source": "structured_current_fact",
        "fact": fact,
        "provenance": {
            "source_type": fact["source_type"],
            "source_reference": fact.get("source_reference"),
            "source_memory_ids": fact.get("source_memory_ids", []),
            "privacy_scope": fact["privacy_scope"],
            "reviewed_by": fact.get("reviewed_by"),
            "reviewed_at": fact.get("reviewed_at"),
            "last_verified_at": fact.get("last_verified_at"),
        },
    }


def format_fact_for_context(fact: dict[str, Any]) -> str:
    return (
        f"{fact['subject']} {fact['predicate']} {fact['object_value']} "
        f"(reviewed_by={fact.get('reviewed_by')}, privacy_scope={fact.get('privacy_scope')}, "
        f"fact_id={fact.get('fact_id')})"
    )


def _cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--search")
    parser.add_argument("--history", nargs=2, metavar=("SUBJECT", "PREDICATE"))
    args = parser.parse_args()
    if args.search:
        print(json.dumps(search_facts(args.search, db_path=args.db), indent=2))
    elif args.history:
        print(json.dumps(list_fact_history(args.history[0], args.history[1], db_path=args.db), indent=2))
    else:
        with connect(args.db) as db:
            counts = db.execute("SELECT status, count(*) FROM structured_facts GROUP BY status").fetchall()
        print(json.dumps({"db": args.db, "status_counts": dict(counts)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
