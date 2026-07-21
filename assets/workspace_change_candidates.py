#!/usr/bin/env python3
"""Review-gated workspace change candidates.

This layer compares two reviewed, time-bounded workspace snapshots and proposes
changes. It does not create asset observations, structured facts, tasks, or
Executive Context writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets import workspace_state_candidates as workspace_state
from core.outcome_vocabulary import render_outcome_claim

DEFAULT_DB_PATH = BASE / "memory" / "workspace_change_candidates.sqlite"
MODULE_VERSION = "review_gated_workspace_change_detection_v1"

CHANGE_TYPES = {
    "appeared",
    "disappeared",
    "moved",
    "relationship_changed",
    "unchanged",
    "unable_to_determine",
}
REVIEW_STATUSES = {"pending_review", "approved", "corrected", "rejected"}
REVIEWED_RELATIONSHIP_STATUSES = {"approved", "corrected"}


class WorkspaceChangeError(RuntimeError):
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


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


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
        CREATE TABLE IF NOT EXISTS workspace_change_comparisons (
            comparison_id TEXT PRIMARY KEY,
            snapshot_a_id TEXT NOT NULL,
            snapshot_b_id TEXT NOT NULL,
            snapshot_a_time TEXT,
            snapshot_b_time TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source_fingerprint TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_change_candidates (
            change_candidate_id TEXT PRIMARY KEY,
            comparison_id TEXT NOT NULL,
            snapshot_a_id TEXT NOT NULL,
            snapshot_b_id TEXT NOT NULL,
            subject_label TEXT NOT NULL,
            change_type TEXT NOT NULL,
            object_label TEXT,
            relation TEXT,
            original_subject_label TEXT NOT NULL,
            original_change_type TEXT NOT NULL,
            original_object_label TEXT,
            original_relation TEXT,
            snapshot_a_evidence TEXT NOT NULL DEFAULT '{}',
            snapshot_b_evidence TEXT NOT NULL DEFAULT '{}',
            confidence REAL NOT NULL DEFAULT 0.0,
            uncertainty TEXT NOT NULL DEFAULT '[]',
            review_status TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by TEXT,
            review_reason TEXT,
            fingerprint TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_change_candidate_events (
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
    db.execute("CREATE INDEX IF NOT EXISTS idx_workspace_change_comparison ON workspace_change_candidates(comparison_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_workspace_change_review_status ON workspace_change_candidates(review_status)")
    db.commit()


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
        INSERT INTO workspace_change_candidate_events
        (entity_id, entity_type, operation, actor, reason, timestamp, previous_state, resulting_state)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (entity_id, entity_type, operation, actor, reason, timestamp, _state(previous), _state(resulting)),
    )


def _row_to_comparison(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["metadata"] = _load_json(item.get("metadata"), {})
    return item


def _row_to_change(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for key, default in (
        ("snapshot_a_evidence", {}),
        ("snapshot_b_evidence", {}),
        ("uncertainty", []),
        ("metadata", {}),
    ):
        item[key] = _load_json(item.get(key), default)
    return item


def _evidence_payload(
    *,
    object_labels: list[str] | None = None,
    relationship_ids: list[str] | None = None,
    candidate_ids: list[str] | None = None,
    timestamps: list[float] | None = None,
    frame_hashes: list[str] | None = None,
    coverage_key: str | None = None,
) -> dict[str, Any]:
    return {
        "object_labels": sorted({str(v) for v in (object_labels or []) if v}),
        "relationship_ids": sorted({str(v) for v in (relationship_ids or []) if v}),
        "supporting_candidate_ids": sorted({str(v) for v in (candidate_ids or []) if v}),
        "supporting_timestamps": sorted({float(v) for v in (timestamps or [])}),
        "source_frame_hashes": sorted({str(v) for v in (frame_hashes or []) if v}),
        "coverage_key": coverage_key,
    }


def _merge_evidence(items: list[dict[str, Any]], *, coverage_key: str | None) -> dict[str, Any]:
    labels: list[str] = []
    relationships: list[str] = []
    candidates: list[str] = []
    timestamps: list[float] = []
    hashes: list[str] = []
    for item in items:
        labels.extend(item.get("object_labels") or [])
        if item.get("relationship_id"):
            relationships.append(item["relationship_id"])
        relationships.extend(item.get("relationship_ids") or [])
        candidates.extend(item.get("supporting_candidate_ids") or [])
        candidates.extend(item.get("supporting_visual_candidate_ids") or [])
        timestamps.extend(item.get("supporting_timestamps") or [])
        hashes.extend(item.get("source_frame_hashes") or [])
        hashes.extend(item.get("supporting_frame_hashes") or [])
    return _evidence_payload(
        object_labels=labels,
        relationship_ids=relationships,
        candidate_ids=candidates,
        timestamps=timestamps,
        frame_hashes=hashes,
        coverage_key=coverage_key,
    )


def snapshot_from_workspace_state(
    snapshot_id: str,
    *,
    workspace_db_path: str | Path | None = None,
) -> dict[str, Any]:
    snapshot = workspace_state.get_snapshot(snapshot_id, db_path=workspace_db_path)
    if not snapshot:
        raise WorkspaceChangeError(f"workspace snapshot not found: {snapshot_id}")
    relationships = [
        rel for rel in workspace_state.list_relationships(snapshot_id=snapshot_id, db_path=workspace_db_path)
        if rel.get("status") in REVIEWED_RELATIONSHIP_STATUSES
    ]
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "capture_started_at": snapshot.get("created_at"),
        "capture_ended_at": snapshot.get("reviewed_at") or snapshot.get("created_at"),
        "time_bounds": {
            "start_timestamp": snapshot["start_timestamp"],
            "end_timestamp": snapshot["end_timestamp"],
            "supporting_timestamps": snapshot.get("supporting_timestamps", []),
        },
        "time_bounded": True,
        "coverage_key": (snapshot.get("metadata") or {}).get("coverage_key") or snapshot["source_video_candidate_id"],
        "relationships": [
            {
                "relationship_id": rel["relationship_candidate_id"],
                "subject": rel["subject_label"],
                "relation": rel["relation"],
                "object": rel["object_label"],
                "status": rel["status"],
                "supporting_candidate_ids": rel.get("supporting_visual_candidate_ids", []),
                "supporting_timestamps": rel.get("supporting_timestamps", []),
                "source_frame_hashes": rel.get("supporting_frame_hashes", []),
                "confidence": rel.get("confidence", 0.0),
                "uncertainty": rel.get("uncertainty", []),
            }
            for rel in relationships
        ],
        "metadata": {
            "source": "assets.workspace_state_candidates",
            "source_video_candidate_id": snapshot["source_video_candidate_id"],
            "relationship_count": len(relationships),
        },
    }


def _snapshot_time(snapshot: dict[str, Any]) -> str | None:
    return snapshot.get("capture_ended_at") or snapshot.get("capture_started_at") or snapshot.get("created_at")


def _assert_comparable_snapshots(snapshot_a: dict[str, Any], snapshot_b: dict[str, Any]) -> None:
    if not snapshot_a.get("snapshot_id") or not snapshot_b.get("snapshot_id"):
        raise WorkspaceChangeError("both snapshots require snapshot_id")
    if snapshot_a["snapshot_id"] == snapshot_b["snapshot_id"]:
        raise WorkspaceChangeError("comparison requires two distinct snapshots")
    if not snapshot_a.get("time_bounded") or not snapshot_b.get("time_bounded"):
        raise WorkspaceChangeError("both snapshots must be time-bounded")
    a_time = _parse_time(_snapshot_time(snapshot_a))
    b_time = _parse_time(_snapshot_time(snapshot_b))
    if a_time and b_time and b_time < a_time:
        raise WorkspaceChangeError("snapshot B must not be earlier than snapshot A")


def _object_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    coverage = snapshot.get("coverage_key")
    index: dict[str, list[dict[str, Any]]] = {}
    for obj in snapshot.get("objects") or []:
        label = str(obj.get("label") or obj.get("object_label") or "").strip()
        if not label:
            continue
        evidence = _merge_evidence([{**obj, "object_labels": [label]}], coverage_key=coverage)
        index.setdefault(normalize_text(label), []).append({"label": label, "evidence": evidence})
    for rel in snapshot.get("relationships") or []:
        if rel.get("status") and rel.get("status") not in REVIEWED_RELATIONSHIP_STATUSES:
            continue
        evidence = _merge_evidence([{**rel, "object_labels": [rel.get("subject", ""), rel.get("object", "")]}], coverage_key=coverage)
        for key_name in ("subject", "object"):
            label = str(rel.get(key_name) or "").strip()
            if label:
                index.setdefault(normalize_text(label), []).append({"label": label, "evidence": evidence})
    return {
        key: {
            "label": values[0]["label"],
            "evidence": _merge_evidence([value["evidence"] for value in values], coverage_key=coverage),
        }
        for key, values in index.items()
    }


def _relationship_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    coverage = snapshot.get("coverage_key")
    index: dict[str, dict[str, Any]] = {}
    for rel in snapshot.get("relationships") or []:
        if rel.get("status") and rel.get("status") not in REVIEWED_RELATIONSHIP_STATUSES:
            continue
        subject = str(rel.get("subject") or "").strip()
        relation = str(rel.get("relation") or "").strip()
        obj = str(rel.get("object") or "").strip()
        if not subject or not relation or not obj:
            continue
        key = "|".join([normalize_text(subject), relation, normalize_text(obj)])
        index[key] = {
            "relationship_id": rel.get("relationship_id"),
            "subject": subject,
            "relation": relation,
            "object": obj,
            "evidence": _merge_evidence([{**rel, "object_labels": [subject, obj]}], coverage_key=coverage),
            "confidence": float(rel.get("confidence", 0.0) or 0.0),
            "uncertainty": list(rel.get("uncertainty") or []),
        }
    return index


def _relationship_pair_index(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    pairs: dict[str, list[dict[str, Any]]] = {}
    for rel in _relationship_index(snapshot).values():
        key = "|".join([normalize_text(rel["subject"]), normalize_text(rel["object"])])
        pairs.setdefault(key, []).append(rel)
    return pairs


def comparison_id_for(snapshot_a_id: str, snapshot_b_id: str) -> str:
    digest = hashlib.sha256(f"{snapshot_a_id}|{snapshot_b_id}|{MODULE_VERSION}".encode()).hexdigest()[:16]
    return f"workspace-comparison-{digest}"


def change_fingerprint(change: dict[str, Any]) -> str:
    payload = {
        "comparison_id": change["comparison_id"],
        "subject": normalize_text(change["subject_label"]),
        "change_type": change["change_type"],
        "object": normalize_text(change.get("object_label") or ""),
        "relation": change.get("relation") or "",
        "a_ids": change["snapshot_a_evidence"].get("supporting_candidate_ids", []),
        "b_ids": change["snapshot_b_evidence"].get("supporting_candidate_ids", []),
    }
    return hashlib.sha256(_json(payload).encode()).hexdigest()


def change_id_for(fingerprint: str) -> str:
    return f"workspace-change-{fingerprint[:16]}"


def _candidate(
    *,
    comparison_id: str,
    snapshot_a_id: str,
    snapshot_b_id: str,
    subject: str,
    change_type: str,
    snapshot_a_evidence: dict[str, Any],
    snapshot_b_evidence: dict[str, Any],
    object_label: str | None = None,
    relation: str | None = None,
    confidence: float = 0.0,
    uncertainty: list[str] | None = None,
    created_at: str,
) -> dict[str, Any]:
    if change_type not in CHANGE_TYPES:
        raise WorkspaceChangeError(f"unsupported change type: {change_type}")
    item = {
        "comparison_id": comparison_id,
        "snapshot_a_id": snapshot_a_id,
        "snapshot_b_id": snapshot_b_id,
        "subject_label": subject,
        "change_type": change_type,
        "object_label": object_label,
        "relation": relation,
        "original_subject_label": subject,
        "original_change_type": change_type,
        "original_object_label": object_label,
        "original_relation": relation,
        "snapshot_a_evidence": snapshot_a_evidence,
        "snapshot_b_evidence": snapshot_b_evidence,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "uncertainty": uncertainty or [],
        "review_status": "pending_review",
        "reviewed_at": None,
        "reviewed_by": None,
        "review_reason": None,
        "created_at": created_at,
        "updated_at": created_at,
        "metadata": {
            "module": MODULE_VERSION,
            "change_is_candidate": True,
            "no_automatic_memory_or_task_writes": True,
        },
    }
    item["fingerprint"] = change_fingerprint(item)
    item["change_candidate_id"] = change_id_for(item["fingerprint"])
    return item


def propose_changes(snapshot_a: dict[str, Any], snapshot_b: dict[str, Any], *, created_at: str | None = None) -> list[dict[str, Any]]:
    _assert_comparable_snapshots(snapshot_a, snapshot_b)
    ts = created_at or utcnow()
    comparison_id = comparison_id_for(snapshot_a["snapshot_id"], snapshot_b["snapshot_id"])
    coverage_a = snapshot_a.get("coverage_key")
    coverage_b = snapshot_b.get("coverage_key")
    objects_a = _object_index(snapshot_a)
    objects_b = _object_index(snapshot_b)
    relationships_a = _relationship_index(snapshot_a)
    relationships_b = _relationship_index(snapshot_b)
    pair_a = _relationship_pair_index(snapshot_a)
    pair_b = _relationship_pair_index(snapshot_b)
    changes: list[dict[str, Any]] = []

    if coverage_a != coverage_b:
        for key in sorted(set(objects_a) | set(objects_b)):
            a = objects_a.get(key, {})
            b = objects_b.get(key, {})
            changes.append(_candidate(
                comparison_id=comparison_id,
                snapshot_a_id=snapshot_a["snapshot_id"],
                snapshot_b_id=snapshot_b["snapshot_id"],
                subject=(b or a)["label"],
                change_type="unable_to_determine",
                snapshot_a_evidence=a.get("evidence", _evidence_payload(coverage_key=coverage_a)),
                snapshot_b_evidence=b.get("evidence", _evidence_payload(coverage_key=coverage_b)),
                confidence=0.2,
                uncertainty=["camera coverage differs; absence or movement cannot be established"],
                created_at=ts,
            ))
        return changes

    for key in sorted(set(objects_a) - set(objects_b)):
        obj = objects_a[key]
        changes.append(_candidate(
            comparison_id=comparison_id,
            snapshot_a_id=snapshot_a["snapshot_id"],
            snapshot_b_id=snapshot_b["snapshot_id"],
            subject=obj["label"],
            change_type="disappeared",
            snapshot_a_evidence=obj["evidence"],
            snapshot_b_evidence=_evidence_payload(coverage_key=coverage_b),
            confidence=0.58,
            uncertainty=["object absent from snapshot B; disappearance is time-bounded, not permanent"],
            created_at=ts,
        ))

    for key in sorted(set(objects_b) - set(objects_a)):
        obj = objects_b[key]
        changes.append(_candidate(
            comparison_id=comparison_id,
            snapshot_a_id=snapshot_a["snapshot_id"],
            snapshot_b_id=snapshot_b["snapshot_id"],
            subject=obj["label"],
            change_type="appeared",
            snapshot_a_evidence=_evidence_payload(coverage_key=coverage_a),
            snapshot_b_evidence=obj["evidence"],
            confidence=0.62,
            uncertainty=["object appears in snapshot B; prior absence is bounded to snapshot A coverage"],
            created_at=ts,
        ))

    handled_pairs: set[str] = set()
    for pair_key in sorted(set(pair_a) & set(pair_b)):
        handled_pairs.add(pair_key)
        a_rels = sorted(pair_a[pair_key], key=lambda item: item["relation"])
        b_rels = sorted(pair_b[pair_key], key=lambda item: item["relation"])
        a_relations = {item["relation"] for item in a_rels}
        b_relations = {item["relation"] for item in b_rels}
        if a_relations == b_relations:
            rel = a_rels[0]
            b_rel = b_rels[0]
            changes.append(_candidate(
                comparison_id=comparison_id,
                snapshot_a_id=snapshot_a["snapshot_id"],
                snapshot_b_id=snapshot_b["snapshot_id"],
                subject=rel["subject"],
                change_type="unchanged",
                object_label=rel["object"],
                relation=rel["relation"],
                snapshot_a_evidence=rel["evidence"],
                snapshot_b_evidence=b_rel["evidence"],
                confidence=min(0.9, max(rel["confidence"], b_rel["confidence"], 0.7)),
                uncertainty=["relationship appears stable across the two time-bounded snapshots"],
                created_at=ts,
            ))
        else:
            rel = a_rels[0]
            b_rel = b_rels[0]
            changes.append(_candidate(
                comparison_id=comparison_id,
                snapshot_a_id=snapshot_a["snapshot_id"],
                snapshot_b_id=snapshot_b["snapshot_id"],
                subject=rel["subject"],
                change_type="relationship_changed",
                object_label=rel["object"],
                relation=b_rel["relation"],
                snapshot_a_evidence=rel["evidence"],
                snapshot_b_evidence=b_rel["evidence"],
                confidence=0.66,
                uncertainty=[f"relationship changed from {rel['relation']} to {b_rel['relation']}; review required"],
                created_at=ts,
            ))

    subjects_a = {normalize_text(rel["subject"]) for rel in relationships_a.values()}
    subjects_b = {normalize_text(rel["subject"]) for rel in relationships_b.values()}
    for subject_key in sorted((subjects_a & subjects_b)):
        a_rels = [rel for rel in relationships_a.values() if normalize_text(rel["subject"]) == subject_key]
        b_rels = [rel for rel in relationships_b.values() if normalize_text(rel["subject"]) == subject_key]
        a_objects = {normalize_text(rel["object"]) for rel in a_rels}
        b_objects = {normalize_text(rel["object"]) for rel in b_rels}
        if a_objects != b_objects:
            rel = sorted(a_rels, key=lambda item: item["object"])[0]
            b_rel = sorted(b_rels, key=lambda item: item["object"])[0]
            pair_key = "|".join([subject_key, normalize_text(rel["object"])])
            if pair_key in handled_pairs:
                continue
            changes.append(_candidate(
                comparison_id=comparison_id,
                snapshot_a_id=snapshot_a["snapshot_id"],
                snapshot_b_id=snapshot_b["snapshot_id"],
                subject=rel["subject"],
                change_type="moved",
                object_label=b_rel["object"],
                relation=b_rel["relation"],
                snapshot_a_evidence=rel["evidence"],
                snapshot_b_evidence=b_rel["evidence"],
                confidence=0.6,
                uncertainty=["object relationship target changed; do not infer who moved it or why"],
                created_at=ts,
            ))

    exact_a = set(relationships_a)
    exact_b = set(relationships_b)
    for key in sorted((exact_a - exact_b)):
        rel = relationships_a[key]
        pair_key = "|".join([normalize_text(rel["subject"]), normalize_text(rel["object"])])
        if pair_key in handled_pairs:
            continue
        changes.append(_candidate(
            comparison_id=comparison_id,
            snapshot_a_id=snapshot_a["snapshot_id"],
            snapshot_b_id=snapshot_b["snapshot_id"],
            subject=rel["subject"],
            change_type="unable_to_determine",
            object_label=rel["object"],
            relation=rel["relation"],
            snapshot_a_evidence=rel["evidence"],
            snapshot_b_evidence=_evidence_payload(coverage_key=coverage_b),
            confidence=0.35,
            uncertainty=["relationship was not repeated in snapshot B; object or location evidence is incomplete"],
            created_at=ts,
        ))

    return changes


def _comparison_record(snapshot_a: dict[str, Any], snapshot_b: dict[str, Any], *, created_at: str) -> dict[str, Any]:
    source = {
        "snapshot_a_id": snapshot_a["snapshot_id"],
        "snapshot_b_id": snapshot_b["snapshot_id"],
        "snapshot_a_time": _snapshot_time(snapshot_a),
        "snapshot_b_time": _snapshot_time(snapshot_b),
        "snapshot_a_relationships": _relationship_index(snapshot_a),
        "snapshot_b_relationships": _relationship_index(snapshot_b),
    }
    fingerprint = hashlib.sha256(_json(source).encode()).hexdigest()
    comparison_id = comparison_id_for(snapshot_a["snapshot_id"], snapshot_b["snapshot_id"])
    return {
        "comparison_id": comparison_id,
        "snapshot_a_id": snapshot_a["snapshot_id"],
        "snapshot_b_id": snapshot_b["snapshot_id"],
        "snapshot_a_time": _snapshot_time(snapshot_a),
        "snapshot_b_time": _snapshot_time(snapshot_b),
        "status": "pending_review",
        "created_at": created_at,
        "updated_at": created_at,
        "source_fingerprint": fingerprint,
        "metadata": {
            "module": MODULE_VERSION,
            "time_bounded": True,
            "outcome_claim": render_outcome_claim({
                "action_id": "workspace_change_comparison",
                "status": "succeeded",
                "evidence_type": "local_artifact",
                "evidence": "local pending-review change candidates created",
                "produced_by_echo": True,
            }),
            "boundaries": {
                "creates_asset_observations": False,
                "creates_structured_facts": False,
                "creates_tasks": False,
                "writes_executive_context": False,
            },
        },
    }


def _insert_comparison(db: sqlite3.Connection, comparison: dict[str, Any]) -> None:
    db.execute(
        """
        INSERT INTO workspace_change_comparisons
        (comparison_id, snapshot_a_id, snapshot_b_id, snapshot_a_time, snapshot_b_time,
         status, created_at, updated_at, source_fingerprint, metadata)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            comparison["comparison_id"],
            comparison["snapshot_a_id"],
            comparison["snapshot_b_id"],
            comparison.get("snapshot_a_time"),
            comparison.get("snapshot_b_time"),
            comparison["status"],
            comparison["created_at"],
            comparison["updated_at"],
            comparison["source_fingerprint"],
            _json(comparison.get("metadata", {})),
        ),
    )


def _insert_change(db: sqlite3.Connection, change: dict[str, Any]) -> None:
    db.execute(
        """
        INSERT INTO workspace_change_candidates (
            change_candidate_id, comparison_id, snapshot_a_id, snapshot_b_id,
            subject_label, change_type, object_label, relation,
            original_subject_label, original_change_type, original_object_label,
            original_relation, snapshot_a_evidence, snapshot_b_evidence, confidence,
            uncertainty, review_status, reviewed_at, reviewed_by, review_reason,
            fingerprint, created_at, updated_at, metadata
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            change["change_candidate_id"],
            change["comparison_id"],
            change["snapshot_a_id"],
            change["snapshot_b_id"],
            change["subject_label"],
            change["change_type"],
            change.get("object_label"),
            change.get("relation"),
            change["original_subject_label"],
            change["original_change_type"],
            change.get("original_object_label"),
            change.get("original_relation"),
            _json(change.get("snapshot_a_evidence", {})),
            _json(change.get("snapshot_b_evidence", {})),
            float(change.get("confidence", 0.0)),
            _json(change.get("uncertainty", [])),
            change["review_status"],
            change.get("reviewed_at"),
            change.get("reviewed_by"),
            change.get("review_reason"),
            change["fingerprint"],
            change["created_at"],
            change["updated_at"],
            _json(change.get("metadata", {})),
        ),
    )


def _update_change(db: sqlite3.Connection, change: dict[str, Any]) -> None:
    db.execute(
        """
        UPDATE workspace_change_candidates SET
            subject_label=?, change_type=?, object_label=?, relation=?,
            snapshot_a_evidence=?, snapshot_b_evidence=?, confidence=?,
            uncertainty=?, review_status=?, reviewed_at=?, reviewed_by=?,
            review_reason=?, updated_at=?, metadata=?
        WHERE change_candidate_id=?
        """,
        (
            change["subject_label"],
            change["change_type"],
            change.get("object_label"),
            change.get("relation"),
            _json(change.get("snapshot_a_evidence", {})),
            _json(change.get("snapshot_b_evidence", {})),
            float(change.get("confidence", 0.0)),
            _json(change.get("uncertainty", [])),
            change["review_status"],
            change.get("reviewed_at"),
            change.get("reviewed_by"),
            change.get("review_reason"),
            change["updated_at"],
            _json(change.get("metadata", {})),
            change["change_candidate_id"],
        ),
    )


def create_comparison(
    snapshot_a: dict[str, Any],
    snapshot_b: dict[str, Any],
    *,
    db_path: str | Path | None = None,
    actor: str = "manual_reviewer",
) -> dict[str, Any]:
    ts = utcnow()
    comparison = _comparison_record(snapshot_a, snapshot_b, created_at=ts)
    proposed = propose_changes(snapshot_a, snapshot_b, created_at=ts)
    created: list[dict[str, Any]] = []
    duplicate: list[dict[str, Any]] = []
    with connect(db_path) as db:
        existing = _row_to_comparison(
            db.execute("SELECT * FROM workspace_change_comparisons WHERE comparison_id=?", (comparison["comparison_id"],)).fetchone()
        )
        if not existing:
            _insert_comparison(db, comparison)
            _write_event(
                db,
                entity_id=comparison["comparison_id"],
                entity_type="comparison",
                operation="create_workspace_change_comparison",
                actor=actor,
                reason="compare reviewed time-bounded workspace snapshots",
                previous=None,
                resulting=comparison,
                timestamp=ts,
            )
        else:
            comparison = existing
        for change in proposed:
            row = db.execute("SELECT * FROM workspace_change_candidates WHERE fingerprint=?", (change["fingerprint"],)).fetchone()
            existing_change = _row_to_change(row)
            if existing_change:
                duplicate.append(existing_change)
                continue
            _insert_change(db, change)
            _write_event(
                db,
                entity_id=change["change_candidate_id"],
                entity_type="change_candidate",
                operation="create_change_candidate",
                actor=actor,
                reason="deterministic comparison of reviewed workspace evidence",
                previous=None,
                resulting=change,
                timestamp=ts,
            )
            created.append(change)
        db.commit()
    return {
        "ok": True,
        "comparison": get_comparison(comparison["comparison_id"], db_path=db_path),
        "created_change_count": len(created),
        "duplicate_change_count": len(duplicate),
        "changes": list_changes(comparison_id=comparison["comparison_id"], db_path=db_path),
    }


def create_comparison_from_workspace_snapshots(
    snapshot_a_id: str,
    snapshot_b_id: str,
    *,
    db_path: str | Path | None = None,
    workspace_db_path: str | Path | None = None,
    actor: str = "manual_reviewer",
) -> dict[str, Any]:
    return create_comparison(
        snapshot_from_workspace_state(snapshot_a_id, workspace_db_path=workspace_db_path),
        snapshot_from_workspace_state(snapshot_b_id, workspace_db_path=workspace_db_path),
        db_path=db_path,
        actor=actor,
    )


def get_comparison(comparison_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as db:
        row = db.execute("SELECT * FROM workspace_change_comparisons WHERE comparison_id=?", (comparison_id,)).fetchone()
    return _row_to_comparison(row)


def get_change(change_candidate_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as db:
        row = db.execute("SELECT * FROM workspace_change_candidates WHERE change_candidate_id=?", (change_candidate_id,)).fetchone()
    return _row_to_change(row)


def list_changes(
    *,
    comparison_id: str | None = None,
    review_status: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if comparison_id:
        clauses.append("comparison_id=?")
        params.append(comparison_id)
    if review_status:
        clauses.append("review_status=?")
        params.append(review_status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(db_path) as db:
        rows = db.execute(
            f"""
            SELECT * FROM workspace_change_candidates {where}
            ORDER BY change_type ASC, subject_label ASC, relation ASC, object_label ASC
            """,
            params,
        ).fetchall()
    return [_row_to_change(row) for row in rows]


def list_events(entity_id: str, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT * FROM workspace_change_candidate_events WHERE entity_id=? ORDER BY event_id ASC",
            (entity_id,),
        ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        event = dict(row)
        event["previous_state"] = _load_json(event.get("previous_state"), None)
        event["resulting_state"] = _load_json(event.get("resulting_state"), {})
        events.append(event)
    return events


def _review_change(
    change_candidate_id: str,
    *,
    review_status: str,
    reviewer: str,
    reason: str,
    subject: str | None = None,
    change_type: str | None = None,
    object_label: str | None = None,
    relation: str | None = None,
    uncertainty: list[str] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if review_status not in {"approved", "corrected", "rejected"}:
        raise WorkspaceChangeError(f"unsupported review status: {review_status}")
    if change_type is not None and change_type not in CHANGE_TYPES:
        raise WorkspaceChangeError(f"unsupported change type: {change_type}")
    if not reviewer:
        raise WorkspaceChangeError("reviewer is required")
    if not reason:
        raise WorkspaceChangeError("review reason is required")
    ts = utcnow()
    with connect(db_path) as db:
        current = _row_to_change(
            db.execute("SELECT * FROM workspace_change_candidates WHERE change_candidate_id=?", (change_candidate_id,)).fetchone()
        )
        if not current:
            raise WorkspaceChangeError(f"change candidate not found: {change_candidate_id}")
        if current["review_status"] == "rejected" and review_status == "approved":
            raise WorkspaceChangeError("rejected change candidates cannot be silently approved")
        previous = dict(current)
        current.update({
            "review_status": review_status,
            "reviewed_at": ts,
            "reviewed_by": reviewer,
            "review_reason": reason,
            "updated_at": ts,
            "subject_label": subject or current["subject_label"],
            "change_type": change_type or current["change_type"],
            "object_label": object_label if object_label is not None else current.get("object_label"),
            "relation": relation if relation is not None else current.get("relation"),
        })
        if uncertainty is not None:
            current["uncertainty"] = uncertainty
        _update_change(db, current)
        _write_event(
            db,
            entity_id=change_candidate_id,
            entity_type="change_candidate",
            operation=f"{review_status}_change_candidate",
            actor=reviewer,
            reason=reason,
            previous=previous,
            resulting=current,
            timestamp=ts,
        )
        db.commit()
    return get_change(change_candidate_id, db_path=db_path)


def approve_change(change_candidate_id: str, *, reviewer: str, reason: str, db_path: str | Path | None = None) -> dict[str, Any]:
    return _review_change(change_candidate_id, review_status="approved", reviewer=reviewer, reason=reason, db_path=db_path)


def correct_change(
    change_candidate_id: str,
    *,
    reviewer: str,
    reason: str,
    subject: str | None = None,
    change_type: str | None = None,
    object_label: str | None = None,
    relation: str | None = None,
    uncertainty: list[str] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if not any([subject, change_type, object_label is not None, relation is not None, uncertainty]):
        raise WorkspaceChangeError("at least one corrected field is required")
    return _review_change(
        change_candidate_id,
        review_status="corrected",
        reviewer=reviewer,
        reason=reason,
        subject=subject,
        change_type=change_type,
        object_label=object_label,
        relation=relation,
        uncertainty=uncertainty,
        db_path=db_path,
    )


def reject_change(change_candidate_id: str, *, reviewer: str, reason: str, db_path: str | Path | None = None) -> dict[str, Any]:
    return _review_change(change_candidate_id, review_status="rejected", reviewer=reviewer, reason=reason, db_path=db_path)


def deterministic_summary(comparison_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    comparison = get_comparison(comparison_id, db_path=db_path)
    if not comparison:
        raise WorkspaceChangeError(f"comparison not found: {comparison_id}")
    changes = list_changes(comparison_id=comparison_id, db_path=db_path)
    return {
        "comparison_id": comparison_id,
        "snapshot_a_id": comparison["snapshot_a_id"],
        "snapshot_b_id": comparison["snapshot_b_id"],
        "status": comparison["status"],
        "change_count": len(changes),
        "review_status_counts": {
            status: sum(1 for item in changes if item["review_status"] == status)
            for status in sorted(REVIEW_STATUSES)
        },
        "changes": [
            {
                "change_candidate_id": item["change_candidate_id"],
                "subject": item["subject_label"],
                "change_type": item["change_type"],
                "relation": item.get("relation"),
                "object": item.get("object_label"),
                "review_status": item["review_status"],
                "confidence": item["confidence"],
                "uncertainty": item["uncertainty"],
                "snapshot_a_timestamps": item["snapshot_a_evidence"].get("supporting_timestamps", []),
                "snapshot_b_timestamps": item["snapshot_b_evidence"].get("supporting_timestamps", []),
            }
            for item in changes
        ],
        "boundaries": {
            "creates_asset_observations": False,
            "creates_structured_facts": False,
            "creates_tasks": False,
            "writes_executive_context": False,
        },
    }


def _load_snapshot_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _self_test() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "assets.workspace_change_candidates",
        "storage": str(DEFAULT_DB_PATH),
        "change_types": sorted(CHANGE_TYPES),
        "review_statuses": sorted(REVIEW_STATUSES),
        "writes_permanent_memory": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("self-test")

    compare_json = sub.add_parser("compare-json")
    compare_json.add_argument("--snapshot-a", type=Path, required=True)
    compare_json.add_argument("--snapshot-b", type=Path, required=True)

    compare_ws = sub.add_parser("compare-workspace")
    compare_ws.add_argument("--snapshot-a-id", required=True)
    compare_ws.add_argument("--snapshot-b-id", required=True)
    compare_ws.add_argument("--workspace-db", type=Path)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--comparison-id")
    list_cmd.add_argument("--review-status")

    show = sub.add_parser("show")
    show.add_argument("--change-id", required=True)

    summary = sub.add_parser("summary")
    summary.add_argument("--comparison-id", required=True)

    approve = sub.add_parser("approve")
    approve.add_argument("--change-id", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--reason", required=True)

    correct = sub.add_parser("correct")
    correct.add_argument("--change-id", required=True)
    correct.add_argument("--subject")
    correct.add_argument("--change-type")
    correct.add_argument("--object-label")
    correct.add_argument("--relation")
    correct.add_argument("--uncertainty", action="append")
    correct.add_argument("--reviewer", required=True)
    correct.add_argument("--reason", required=True)

    reject = sub.add_parser("reject")
    reject.add_argument("--change-id", required=True)
    reject.add_argument("--reviewer", required=True)
    reject.add_argument("--reason", required=True)

    args = parser.parse_args()
    if args.cmd == "self-test":
        _print(_self_test())
    elif args.cmd == "compare-json":
        _print(create_comparison(_load_snapshot_file(args.snapshot_a), _load_snapshot_file(args.snapshot_b), db_path=args.db))
    elif args.cmd == "compare-workspace":
        _print(create_comparison_from_workspace_snapshots(
            args.snapshot_a_id,
            args.snapshot_b_id,
            db_path=args.db,
            workspace_db_path=args.workspace_db,
        ))
    elif args.cmd == "list":
        _print(list_changes(comparison_id=args.comparison_id, review_status=args.review_status, db_path=args.db))
    elif args.cmd == "show":
        _print(get_change(args.change_id, db_path=args.db) or {})
    elif args.cmd == "summary":
        _print(deterministic_summary(args.comparison_id, db_path=args.db))
    elif args.cmd == "approve":
        _print(approve_change(args.change_id, reviewer=args.reviewer, reason=args.reason, db_path=args.db))
    elif args.cmd == "correct":
        _print(correct_change(
            args.change_id,
            reviewer=args.reviewer,
            reason=args.reason,
            subject=args.subject,
            change_type=args.change_type,
            object_label=args.object_label,
            relation=args.relation,
            uncertainty=args.uncertainty,
            db_path=args.db,
        ))
    elif args.cmd == "reject":
        _print(reject_change(args.change_id, reviewer=args.reviewer, reason=args.reason, db_path=args.db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
