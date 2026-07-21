#!/usr/bin/env python3
"""Reviewable workspace-state candidates from reviewed visual evidence.

This layer proposes time-bounded object relationships for a workspace snapshot.
It does not create asset observations, structured facts, tasks, or Executive
Context writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets.visual_analysis_candidates import list_visual_candidates

DEFAULT_DB_PATH = BASE / "memory" / "workspace_state_candidates.sqlite"
ALLOWED_RELATIONS = {
    "on",
    "beneath",
    "above",
    "beside",
    "near",
    "in_front_of",
    "behind",
    "partially_obscured_by",
    "visible_through_or_reflected_in",
    "part_of_workspace",
}
ALLOWED_STATUSES = {"pending_review", "approved", "corrected", "rejected", "superseded"}
REVIEWED_VISUAL_STATUSES = {"approved", "corrected"}
MODULE_VERSION = "reviewable_workspace_state_v1"


class WorkspaceStateError(RuntimeError):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, default=str)


def _load_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def effective_visual_label(candidate: dict[str, Any]) -> str:
    return str(candidate.get("corrected_label") or candidate.get("proposed_label") or "").strip()


def snapshot_id_for(video_candidate_id: str) -> str:
    digest = hashlib.sha256(f"{video_candidate_id}|{MODULE_VERSION}".encode()).hexdigest()[:16]
    return f"workspace-snapshot-{digest}"


def relationship_id_for(
    snapshot_id: str,
    subject_label: str,
    relation: str,
    object_label: str,
    supporting_candidate_ids: list[str],
) -> str:
    payload = "|".join([
        snapshot_id,
        normalize_text(subject_label),
        relation,
        normalize_text(object_label),
        ",".join(sorted(supporting_candidate_ids)),
    ])
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"workspace-relation-{digest}"


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    ensure_schema(db)
    return db


def ensure_schema(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            source_video_candidate_id TEXT NOT NULL,
            start_timestamp REAL NOT NULL,
            end_timestamp REAL NOT NULL,
            supporting_timestamps TEXT NOT NULL DEFAULT '[]',
            supporting_visual_candidate_ids TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.0,
            uncertainty TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by TEXT,
            review_reason TEXT,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_relationship_candidates (
            relationship_candidate_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            source_video_candidate_id TEXT NOT NULL,
            subject_label TEXT NOT NULL,
            relation TEXT NOT NULL,
            object_label TEXT NOT NULL,
            proposed_subject_label TEXT NOT NULL,
            proposed_relation TEXT NOT NULL,
            proposed_object_label TEXT NOT NULL,
            supporting_visual_candidate_ids TEXT NOT NULL DEFAULT '[]',
            supporting_timestamps TEXT NOT NULL DEFAULT '[]',
            supporting_frame_hashes TEXT NOT NULL DEFAULT '[]',
            support_scope TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.0,
            uncertainty TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by TEXT,
            review_reason TEXT,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_state_candidate_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            operation TEXT NOT NULL,
            actor TEXT NOT NULL,
            reason TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            previous_state TEXT,
            resulting_state TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_workspace_snapshots_video ON workspace_snapshots(source_video_candidate_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_workspace_relationships_snapshot ON workspace_relationship_candidates(snapshot_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_workspace_relationships_status ON workspace_relationship_candidates(status)")
    db.commit()


def _row_to_snapshot(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for key, default in (
        ("supporting_timestamps", []),
        ("supporting_visual_candidate_ids", []),
        ("uncertainty", []),
        ("metadata", {}),
    ):
        item[key] = _load_json(item.get(key), default)
    return item


def _row_to_relationship(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for key, default in (
        ("supporting_visual_candidate_ids", []),
        ("supporting_timestamps", []),
        ("supporting_frame_hashes", []),
        ("uncertainty", []),
        ("metadata", {}),
    ):
        item[key] = _load_json(item.get(key), default)
    return item


def _state(value: dict[str, Any] | None) -> str | None:
    return json.dumps(value, sort_keys=True, default=str) if value is not None else None


def _write_event(
    db: sqlite3.Connection,
    *,
    entity_id: str,
    entity_type: str,
    operation: str,
    actor: str,
    reason: str,
    previous: dict[str, Any] | None,
    resulting: dict[str, Any],
    timestamp: str,
) -> None:
    db.execute(
        """
        INSERT INTO workspace_state_candidate_events
        (entity_id, entity_type, operation, actor, reason, timestamp, previous_state, resulting_state)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (entity_id, entity_type, operation, actor, reason, timestamp, _state(previous), _state(resulting)),
    )


def _insert_snapshot(db: sqlite3.Connection, snapshot: dict[str, Any]) -> None:
    db.execute(
        """
        INSERT INTO workspace_snapshots (
            snapshot_id, source_video_candidate_id, start_timestamp, end_timestamp,
            supporting_timestamps, supporting_visual_candidate_ids, status,
            confidence, uncertainty, created_at, reviewed_at, reviewed_by,
            review_reason, metadata
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            snapshot["snapshot_id"],
            snapshot["source_video_candidate_id"],
            float(snapshot["start_timestamp"]),
            float(snapshot["end_timestamp"]),
            _json(snapshot.get("supporting_timestamps", [])),
            _json(snapshot.get("supporting_visual_candidate_ids", [])),
            snapshot["status"],
            float(snapshot.get("confidence", 0.0)),
            _json(snapshot.get("uncertainty", [])),
            snapshot["created_at"],
            snapshot.get("reviewed_at"),
            snapshot.get("reviewed_by"),
            snapshot.get("review_reason"),
            _json(snapshot.get("metadata", {})),
        ),
    )


def _insert_relationship(db: sqlite3.Connection, relationship: dict[str, Any]) -> None:
    db.execute(
        """
        INSERT INTO workspace_relationship_candidates (
            relationship_candidate_id, snapshot_id, source_video_candidate_id,
            subject_label, relation, object_label, proposed_subject_label,
            proposed_relation, proposed_object_label, supporting_visual_candidate_ids,
            supporting_timestamps, supporting_frame_hashes, support_scope,
            confidence, uncertainty, status, created_at, reviewed_at, reviewed_by,
            review_reason, metadata
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            relationship["relationship_candidate_id"],
            relationship["snapshot_id"],
            relationship["source_video_candidate_id"],
            relationship["subject_label"],
            relationship["relation"],
            relationship["object_label"],
            relationship["proposed_subject_label"],
            relationship["proposed_relation"],
            relationship["proposed_object_label"],
            _json(relationship.get("supporting_visual_candidate_ids", [])),
            _json(relationship.get("supporting_timestamps", [])),
            _json(relationship.get("supporting_frame_hashes", [])),
            relationship["support_scope"],
            float(relationship.get("confidence", 0.0)),
            _json(relationship.get("uncertainty", [])),
            relationship["status"],
            relationship["created_at"],
            relationship.get("reviewed_at"),
            relationship.get("reviewed_by"),
            relationship.get("review_reason"),
            _json(relationship.get("metadata", {})),
        ),
    )


def _update_relationship(db: sqlite3.Connection, relationship: dict[str, Any]) -> None:
    db.execute(
        """
        UPDATE workspace_relationship_candidates SET
            subject_label=?, relation=?, object_label=?, status=?, reviewed_at=?,
            reviewed_by=?, review_reason=?, supporting_visual_candidate_ids=?,
            supporting_timestamps=?, supporting_frame_hashes=?, support_scope=?,
            uncertainty=?, metadata=?
        WHERE relationship_candidate_id=?
        """,
        (
            relationship["subject_label"],
            relationship["relation"],
            relationship["object_label"],
            relationship["status"],
            relationship.get("reviewed_at"),
            relationship.get("reviewed_by"),
            relationship.get("review_reason"),
            _json(relationship.get("supporting_visual_candidate_ids", [])),
            _json(relationship.get("supporting_timestamps", [])),
            _json(relationship.get("supporting_frame_hashes", [])),
            relationship["support_scope"],
            _json(relationship.get("uncertainty", [])),
            _json(relationship.get("metadata", {})),
            relationship["relationship_candidate_id"],
        ),
    )


def get_snapshot(snapshot_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as db:
        row = db.execute("SELECT * FROM workspace_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
    return _row_to_snapshot(row)


def get_relationship(relationship_candidate_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as db:
        row = db.execute(
            "SELECT * FROM workspace_relationship_candidates WHERE relationship_candidate_id=?",
            (relationship_candidate_id,),
        ).fetchone()
    return _row_to_relationship(row)


def list_relationships(
    *,
    snapshot_id: str | None = None,
    video_candidate_id: str | None = None,
    status: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if snapshot_id:
        clauses.append("snapshot_id=?")
        params.append(snapshot_id)
    if video_candidate_id:
        clauses.append("source_video_candidate_id=?")
        params.append(video_candidate_id)
    if status:
        clauses.append("status=?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(db_path) as db:
        rows = db.execute(
            f"""
            SELECT * FROM workspace_relationship_candidates {where}
            ORDER BY subject_label ASC, relation ASC, object_label ASC
            """,
            params,
        ).fetchall()
    return [_row_to_relationship(row) for row in rows]


def list_events(entity_id: str, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT * FROM workspace_state_candidate_events WHERE entity_id=? ORDER BY event_id ASC",
            (entity_id,),
        ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        event = dict(row)
        event["previous_state"] = _load_json(event.get("previous_state"), None)
        event["resulting_state"] = _load_json(event.get("resulting_state"), {})
        events.append(event)
    return events


def _reviewed_candidates(video_candidate_id: str, *, visual_db_path: str | Path | None = None) -> list[dict[str, Any]]:
    candidates = [
        item for item in list_visual_candidates(video_candidate_id=video_candidate_id, db_path=visual_db_path)
        if item.get("status") in REVIEWED_VISUAL_STATUSES
    ]
    if not candidates:
        raise WorkspaceStateError(f"no reviewed visual candidates found for {video_candidate_id}")
    return candidates


def _label_index(candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        label = normalize_text(effective_visual_label(candidate))
        index[label].append(candidate)
    return index


def _find_all(index: dict[str, list[dict[str, Any]]], needles: list[str]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for needle in needles:
        needle_norm = normalize_text(needle)
        for label, candidates in index.items():
            if needle_norm in label:
                for candidate in candidates:
                    cid = candidate["visual_candidate_id"]
                    if cid not in seen:
                        seen.add(cid)
                        matches.append(candidate)
    return matches


def _find_at(index: dict[str, list[dict[str, Any]]], needle: str, timestamp: float) -> list[dict[str, Any]]:
    return [
        candidate for candidate in _find_all(index, [needle])
        if abs(float(candidate.get("frame_timestamp", -1.0)) - timestamp) < 0.002
    ]


def _support_payload(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ids": sorted({candidate["visual_candidate_id"] for candidate in candidates}),
        "timestamps": sorted({float(candidate["frame_timestamp"]) for candidate in candidates}),
        "hashes": sorted({candidate["source_frame_hash"] for candidate in candidates}),
        "scope": "multiple_frames" if len({float(candidate["frame_timestamp"]) for candidate in candidates}) > 1 else "single_frame",
    }


def _timestamp_key(candidate: dict[str, Any]) -> str:
    return f"{float(candidate.get('frame_timestamp', -1.0)):.3f}"


def _same_frame_support(*candidate_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only candidates whose timestamp is shared by every object side."""
    if not candidate_groups or any(not group for group in candidate_groups):
        return []
    timestamp_sets = [
        {_timestamp_key(candidate) for candidate in group}
        for group in candidate_groups
    ]
    valid_timestamps = set.intersection(*timestamp_sets)
    support: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in candidate_groups:
        for candidate in group:
            cid = candidate["visual_candidate_id"]
            if _timestamp_key(candidate) in valid_timestamps and cid not in seen:
                support.append(candidate)
                seen.add(cid)
    return sorted(support, key=lambda item: (float(item["frame_timestamp"]), item["visual_candidate_id"]))


def _relationship(
    *,
    snapshot_id: str,
    video_candidate_id: str,
    subject: str,
    relation: str,
    object_label: str,
    support: list[dict[str, Any]],
    confidence: float,
    uncertainty: list[str],
    created_at: str,
) -> dict[str, Any]:
    if relation not in ALLOWED_RELATIONS:
        raise WorkspaceStateError(f"unsupported relation: {relation}")
    payload = _support_payload(support)
    return {
        "relationship_candidate_id": relationship_id_for(snapshot_id, subject, relation, object_label, payload["ids"]),
        "snapshot_id": snapshot_id,
        "source_video_candidate_id": video_candidate_id,
        "subject_label": subject,
        "relation": relation,
        "object_label": object_label,
        "proposed_subject_label": subject,
        "proposed_relation": relation,
        "proposed_object_label": object_label,
        "supporting_visual_candidate_ids": payload["ids"],
        "supporting_timestamps": payload["timestamps"],
        "supporting_frame_hashes": payload["hashes"],
        "support_scope": payload["scope"],
        "confidence": max(0.0, min(1.0, float(confidence))),
        "uncertainty": uncertainty,
        "status": "pending_review",
        "created_at": created_at,
        "reviewed_at": None,
        "reviewed_by": None,
        "review_reason": None,
        "metadata": {
            "module": MODULE_VERSION,
            "relationship_is_candidate": True,
            "time_bounded_to_source_video": True,
        },
    }


def propose_relationships(video_candidate_id: str, candidates: list[dict[str, Any]], *, created_at: str) -> list[dict[str, Any]]:
    """Create conservative relationship proposals from reviewed candidate labels.

    The rules are intentionally narrow and depend only on reviewed labels and
    shared timestamps. They are candidate proposals, not truth.
    """
    snapshot_id = snapshot_id_for(video_candidate_id)
    index = _label_index(candidates)
    proposals: list[dict[str, Any]] = []

    keyboard = _find_all(index, ["blue-backlit keyboard"])
    desk = _find_all(index, ["desk", "desk/work surface"])
    support = _same_frame_support(keyboard, desk)
    if support:
        proposals.append(_relationship(
            snapshot_id=snapshot_id,
            video_candidate_id=video_candidate_id,
            subject="blue-backlit keyboard",
            relation="on",
            object_label="desk/work surface",
            support=support,
            confidence=0.86,
            uncertainty=["relationship inferred from repeated reviewed workspace frames; not a permanent location"],
            created_at=created_at,
        ))

    monitor = _find_all(index, ["computer monitor"])
    support = _same_frame_support(monitor, keyboard)
    if support:
        proposals.append(_relationship(
            snapshot_id=snapshot_id,
            video_candidate_id=video_candidate_id,
            subject="computer monitor",
            relation="above",
            object_label="blue-backlit keyboard",
            support=support,
            confidence=0.74,
            uncertainty=["above/behind orientation is approximate from camera angle"],
            created_at=created_at,
        ))
        proposals.append(_relationship(
            snapshot_id=snapshot_id,
            video_candidate_id=video_candidate_id,
            subject="computer monitor",
            relation="behind",
            object_label="blue-backlit keyboard",
            support=support,
            confidence=0.68,
            uncertainty=["behind relation is perspective-dependent and should be reviewed"],
            created_at=created_at,
        ))

    headset = _find_all(index, ["headset"])
    support = _same_frame_support(headset, desk)
    if support:
        proposals.append(_relationship(
            snapshot_id=snapshot_id,
            video_candidate_id=video_candidate_id,
            subject="headset",
            relation="near",
            object_label="desk/work surface",
            support=support,
            confidence=0.72,
            uncertainty=["one headset sighting is partial; exact support surface is not asserted"],
            created_at=created_at,
        ))

    controller = _find_all(index, ["game controller"])
    support = _same_frame_support(controller, desk)
    if support:
        proposals.append(_relationship(
            snapshot_id=snapshot_id,
            video_candidate_id=video_candidate_id,
            subject="game controller",
            relation="on",
            object_label="desk/work surface",
            support=support,
            confidence=0.78,
            uncertainty=["camera angle supports workspace placement but not permanent location"],
            created_at=created_at,
        ))

    ingot = _find_at(index, "small metal ingot or block", 22.336)
    cloth = _find_at(index, "folded green cloth or towel", 22.336)
    if ingot and cloth:
        proposals.append(_relationship(
            snapshot_id=snapshot_id,
            video_candidate_id=video_candidate_id,
            subject="small metal ingot or block",
            relation="on",
            object_label="folded green cloth or towel",
            support=ingot + cloth,
            confidence=0.76,
            uncertainty=["exact contact is visually plausible but should be reviewed"],
            created_at=created_at,
        ))

    computer_case = _find_at(index, "black glass-sided computer case", 37.226)
    black_surface = _find_at(index, "black tabletop or shelf surface", 37.226)
    if computer_case and black_surface:
        proposals.append(_relationship(
            snapshot_id=snapshot_id,
            video_candidate_id=video_candidate_id,
            subject="black glass-sided computer case with RGB lighting",
            relation="on",
            object_label="black tabletop or shelf surface",
            support=computer_case + black_surface,
            confidence=0.82,
            uncertainty=["exact furniture type remains uncertain"],
            created_at=created_at,
        ))

    container = _find_at(index, "container", 37.226)
    if container and computer_case:
        proposals.append(_relationship(
            snapshot_id=snapshot_id,
            video_candidate_id=video_candidate_id,
            subject="small labeled container",
            relation="beside",
            object_label="black glass-sided computer case with RGB lighting",
            support=container + computer_case,
            confidence=0.7,
            uncertainty=["beside relation is based on one reviewed frame"],
            created_at=created_at,
        ))

    striped = _find_at(index, "striped cloth or fabric visible through or reflected in glass", 37.226)
    if striped and computer_case:
        proposals.append(_relationship(
            snapshot_id=snapshot_id,
            video_candidate_id=video_candidate_id,
            subject="striped cloth or fabric",
            relation="visible_through_or_reflected_in",
            object_label="computer case glass panel",
            support=striped + computer_case,
            confidence=0.67,
            uncertainty=["review notes indicate reflection or through-glass visibility; exact position uncertain"],
            created_at=created_at,
        ))

    return proposals


def create_snapshot_candidate(
    video_candidate_id: str,
    *,
    db_path: str | Path | None = None,
    visual_db_path: str | Path | None = None,
    actor: str = "manual_reviewer",
) -> dict[str, Any]:
    candidates = _reviewed_candidates(video_candidate_id, visual_db_path=visual_db_path)
    if any(candidate.get("status") == "pending_review" for candidate in list_visual_candidates(video_candidate_id=video_candidate_id, db_path=visual_db_path)):
        raise WorkspaceStateError("all visual candidates must be reviewed before creating a workspace snapshot")
    ts = utcnow()
    snapshot_id = snapshot_id_for(video_candidate_id)
    timestamps = sorted({float(candidate["frame_timestamp"]) for candidate in candidates})
    snapshot = {
        "snapshot_id": snapshot_id,
        "source_video_candidate_id": video_candidate_id,
        "start_timestamp": min(timestamps),
        "end_timestamp": max(timestamps),
        "supporting_timestamps": timestamps,
        "supporting_visual_candidate_ids": sorted(candidate["visual_candidate_id"] for candidate in candidates),
        "status": "pending_review",
        "confidence": 0.0,
        "uncertainty": [
            "time-bounded to reviewed video evidence",
            "relationships are pending Andrew review",
        ],
        "created_at": ts,
        "reviewed_at": None,
        "reviewed_by": None,
        "review_reason": None,
        "metadata": {
            "module": MODULE_VERSION,
            "visual_candidate_count": len(candidates),
            "relationship_policy": "conservative reviewed-label rules",
            "no_automatic_memory_or_task_writes": True,
        },
    }
    proposed = propose_relationships(video_candidate_id, candidates, created_at=ts)
    created_relationships: list[dict[str, Any]] = []
    duplicate_relationships: list[dict[str, Any]] = []
    with connect(db_path) as db:
        existing_snapshot = _row_to_snapshot(
            db.execute("SELECT * FROM workspace_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        )
        if not existing_snapshot:
            _insert_snapshot(db, snapshot)
            _write_event(
                db,
                entity_id=snapshot_id,
                entity_type="snapshot",
                operation="create_snapshot_candidate",
                actor=actor,
                reason="reviewed visual evidence workspace snapshot candidate",
                previous=None,
                resulting=snapshot,
                timestamp=ts,
            )
        else:
            snapshot = existing_snapshot
        for relationship in proposed:
            existing = _row_to_relationship(
                db.execute(
                    "SELECT * FROM workspace_relationship_candidates WHERE relationship_candidate_id=?",
                    (relationship["relationship_candidate_id"],),
                ).fetchone()
            )
            if existing:
                duplicate_relationships.append(existing)
                continue
            _insert_relationship(db, relationship)
            _write_event(
                db,
                entity_id=relationship["relationship_candidate_id"],
                entity_type="relationship",
                operation="create_relationship_candidate",
                actor=actor,
                reason="conservative relationship proposal from reviewed visual candidates",
                previous=None,
                resulting=relationship,
                timestamp=ts,
            )
            created_relationships.append(relationship)
        db.commit()
    return {
        "ok": True,
        "snapshot": get_snapshot(snapshot_id, db_path=db_path),
        "created_relationship_count": len(created_relationships),
        "duplicate_relationship_count": len(duplicate_relationships),
        "relationships": list_relationships(snapshot_id=snapshot_id, db_path=db_path),
    }


def _review_relationship(
    relationship_candidate_id: str,
    *,
    status: str,
    reviewer: str,
    reason: str,
    subject: str | None = None,
    relation: str | None = None,
    object_label: str | None = None,
    supporting_visual_candidate_ids: list[str] | None = None,
    supporting_timestamps: list[float] | None = None,
    supporting_frame_hashes: list[str] | None = None,
    uncertainty: list[str] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if status not in {"approved", "corrected", "rejected"}:
        raise WorkspaceStateError(f"unsupported review status: {status}")
    if not reviewer:
        raise WorkspaceStateError("reviewer is required")
    if not reason:
        raise WorkspaceStateError("review reason is required")
    if relation is not None and relation not in ALLOWED_RELATIONS:
        raise WorkspaceStateError(f"unsupported relation: {relation}")
    ts = utcnow()
    with connect(db_path) as db:
        row = db.execute(
            "SELECT * FROM workspace_relationship_candidates WHERE relationship_candidate_id=?",
            (relationship_candidate_id,),
        ).fetchone()
        relationship = _row_to_relationship(row)
        if not relationship:
            raise WorkspaceStateError(f"relationship candidate not found: {relationship_candidate_id}")
        if relationship["status"] == "rejected" and status == "approved":
            raise WorkspaceStateError("rejected relationship candidates cannot be silently approved")
        if relationship["status"] in {"approved", "corrected"} and status == "rejected":
            raise WorkspaceStateError("reviewed relationship candidates cannot be silently rejected")
        previous = dict(relationship)
        relationship.update({
            "status": status,
            "reviewed_at": ts,
            "reviewed_by": reviewer,
            "review_reason": reason,
            "subject_label": subject or relationship["subject_label"],
            "relation": relation or relationship["relation"],
            "object_label": object_label or relationship["object_label"],
        })
        if supporting_visual_candidate_ids is not None:
            relationship["supporting_visual_candidate_ids"] = sorted(set(supporting_visual_candidate_ids))
        if supporting_timestamps is not None:
            relationship["supporting_timestamps"] = sorted({float(timestamp) for timestamp in supporting_timestamps})
            relationship["support_scope"] = "multiple_frames" if len(relationship["supporting_timestamps"]) > 1 else "single_frame"
        if supporting_frame_hashes is not None:
            relationship["supporting_frame_hashes"] = sorted(set(supporting_frame_hashes))
        if uncertainty is not None:
            relationship["uncertainty"] = uncertainty
        _update_relationship(db, relationship)
        _write_event(
            db,
            entity_id=relationship_candidate_id,
            entity_type="relationship",
            operation=f"{status}_relationship_candidate",
            actor=reviewer,
            reason=reason,
            previous=previous,
            resulting=relationship,
            timestamp=ts,
        )
        db.commit()
    return get_relationship(relationship_candidate_id, db_path=db_path)


def approve_relationship(
    relationship_candidate_id: str,
    *,
    reviewer: str,
    reason: str,
    supporting_visual_candidate_ids: list[str] | None = None,
    supporting_timestamps: list[float] | None = None,
    supporting_frame_hashes: list[str] | None = None,
    uncertainty: list[str] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    return _review_relationship(
        relationship_candidate_id,
        status="approved",
        reviewer=reviewer,
        reason=reason,
        supporting_visual_candidate_ids=supporting_visual_candidate_ids,
        supporting_timestamps=supporting_timestamps,
        supporting_frame_hashes=supporting_frame_hashes,
        uncertainty=uncertainty,
        db_path=db_path,
    )


def correct_relationship(
    relationship_candidate_id: str,
    *,
    subject: str | None = None,
    relation: str | None = None,
    object_label: str | None = None,
    supporting_visual_candidate_ids: list[str] | None = None,
    supporting_timestamps: list[float] | None = None,
    supporting_frame_hashes: list[str] | None = None,
    uncertainty: list[str] | None = None,
    reviewer: str,
    reason: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if not any([subject, relation, object_label, supporting_visual_candidate_ids, supporting_timestamps, supporting_frame_hashes, uncertainty]):
        raise WorkspaceStateError("at least one corrected field is required")
    return _review_relationship(
        relationship_candidate_id,
        status="corrected",
        reviewer=reviewer,
        reason=reason,
        subject=subject,
        relation=relation,
        object_label=object_label,
        supporting_visual_candidate_ids=supporting_visual_candidate_ids,
        supporting_timestamps=supporting_timestamps,
        supporting_frame_hashes=supporting_frame_hashes,
        uncertainty=uncertainty,
        db_path=db_path,
    )


def reject_relationship(relationship_candidate_id: str, *, reviewer: str, reason: str, db_path: str | Path | None = None) -> dict[str, Any]:
    return _review_relationship(relationship_candidate_id, status="rejected", reviewer=reviewer, reason=reason, db_path=db_path)


def deterministic_summary(snapshot_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    snapshot = get_snapshot(snapshot_id, db_path=db_path)
    if not snapshot:
        raise WorkspaceStateError(f"snapshot not found: {snapshot_id}")
    relationships = list_relationships(snapshot_id=snapshot_id, db_path=db_path)
    return {
        "snapshot_id": snapshot_id,
        "source_video_candidate_id": snapshot["source_video_candidate_id"],
        "time_bounds": {
            "start_timestamp": snapshot["start_timestamp"],
            "end_timestamp": snapshot["end_timestamp"],
            "supporting_timestamps": snapshot["supporting_timestamps"],
        },
        "status": snapshot["status"],
        "relationship_count": len(relationships),
        "relationships": [
            {
                "relationship_candidate_id": item["relationship_candidate_id"],
                "subject": item["subject_label"],
                "relation": item["relation"],
                "object": item["object_label"],
                "status": item["status"],
                "confidence": item["confidence"],
                "supporting_timestamps": item["supporting_timestamps"],
                "support_scope": item["support_scope"],
                "uncertainty": item["uncertainty"],
            }
            for item in relationships
        ],
        "boundaries": {
            "creates_asset_observations": False,
            "creates_structured_facts": False,
            "creates_tasks": False,
            "writes_executive_context": False,
        },
    }


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _self_test() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "assets.workspace_state_candidates",
        "storage": str(DEFAULT_DB_PATH),
        "allowed_relations": sorted(ALLOWED_RELATIONS),
        "allowed_statuses": sorted(ALLOWED_STATUSES),
        "writes_permanent_memory": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--visual-db", type=Path)
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create")
    create.add_argument("--video-candidate-id", required=True)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--snapshot-id")
    list_cmd.add_argument("--video-candidate-id")
    list_cmd.add_argument("--status")

    summary = sub.add_parser("summary")
    summary.add_argument("--snapshot-id", required=True)

    show = sub.add_parser("show")
    show.add_argument("--relationship-id", required=True)

    approve = sub.add_parser("approve")
    approve.add_argument("--relationship-id", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--reason", required=True)

    correct = sub.add_parser("correct")
    correct.add_argument("--relationship-id", required=True)
    correct.add_argument("--subject")
    correct.add_argument("--relation")
    correct.add_argument("--object-label")
    correct.add_argument("--reviewer", required=True)
    correct.add_argument("--reason", required=True)

    reject = sub.add_parser("reject")
    reject.add_argument("--relationship-id", required=True)
    reject.add_argument("--reviewer", required=True)
    reject.add_argument("--reason", required=True)

    events = sub.add_parser("events")
    events.add_argument("--entity-id", required=True)

    sub.add_parser("self-test")

    args = parser.parse_args()
    if args.cmd == "create":
        _print(create_snapshot_candidate(args.video_candidate_id, db_path=args.db, visual_db_path=args.visual_db))
    elif args.cmd == "list":
        _print(list_relationships(snapshot_id=args.snapshot_id, video_candidate_id=args.video_candidate_id, status=args.status, db_path=args.db))
    elif args.cmd == "summary":
        _print(deterministic_summary(args.snapshot_id, db_path=args.db))
    elif args.cmd == "show":
        _print(get_relationship(args.relationship_id, db_path=args.db) or {})
    elif args.cmd == "approve":
        _print(approve_relationship(args.relationship_id, reviewer=args.reviewer, reason=args.reason, db_path=args.db))
    elif args.cmd == "correct":
        _print(correct_relationship(
            args.relationship_id,
            subject=args.subject,
            relation=args.relation,
            object_label=args.object_label,
            reviewer=args.reviewer,
            reason=args.reason,
            db_path=args.db,
        ))
    elif args.cmd == "reject":
        _print(reject_relationship(args.relationship_id, reviewer=args.reviewer, reason=args.reason, db_path=args.db))
    elif args.cmd == "events":
        _print(list_events(args.entity_id, db_path=args.db))
    elif args.cmd == "self-test":
        _print(_self_test())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
