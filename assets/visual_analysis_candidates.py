#!/usr/bin/env python3
"""Reviewable visual-analysis candidates for video evidence frames.

The module stores tentative visual labels linked to existing video candidate
frames. It does not create asset observations, structured facts, tasks, or
Executive Context changes.
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

from PIL import Image

from assets.video_observation_candidates import get_candidate as get_video_candidate

DEFAULT_DB_PATH = BASE / "memory" / "visual_analysis_candidates.sqlite"
ALLOWED_STATUSES = {"pending_review", "approved", "corrected", "rejected", "superseded"}
NO_MODEL_METHOD = "no_local_vision_model_v1"


class VisualAnalysisError(RuntimeError):
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


def normalize_label(label: str) -> str:
    return " ".join(label.strip().lower().replace("_", " ").split())


def visual_candidate_id_for(video_candidate_id: str, frame_hash: str, normalized_label: str, method: str) -> str:
    digest = hashlib.sha256(f"{video_candidate_id}|{frame_hash}|{normalized_label}|{method}".encode()).hexdigest()[:16]
    return f"visual-candidate-{digest}"


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
        CREATE TABLE IF NOT EXISTS visual_analysis_candidates (
            visual_candidate_id TEXT PRIMARY KEY,
            source_video_candidate_id TEXT NOT NULL,
            source_frame_reference TEXT NOT NULL,
            source_frame_hash TEXT NOT NULL,
            frame_timestamp REAL NOT NULL,
            proposed_label TEXT NOT NULL,
            normalized_label TEXT NOT NULL,
            broad_category TEXT,
            confidence REAL NOT NULL DEFAULT 0.0,
            evidence_region TEXT NOT NULL DEFAULT '{}',
            source_model TEXT NOT NULL,
            model_version TEXT NOT NULL,
            analysis_method_version TEXT NOT NULL,
            processing_timestamp TEXT NOT NULL,
            uncertainty TEXT NOT NULL DEFAULT '[]',
            alternate_labels TEXT NOT NULL DEFAULT '[]',
            privacy_scope TEXT NOT NULL DEFAULT 'owner_private',
            status TEXT NOT NULL,
            reviewed_by TEXT,
            reviewed_at TEXT,
            review_reason TEXT,
            corrected_label TEXT,
            approved_observation_id INTEGER,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS visual_analysis_candidate_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            visual_candidate_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            actor TEXT NOT NULL,
            reason TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            previous_state TEXT,
            resulting_state TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_visual_candidates_video ON visual_analysis_candidates(source_video_candidate_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_visual_candidates_status ON visual_analysis_candidates(status)")
    db.commit()


def _row_to_candidate(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for key, default in (
        ("source_frame_reference", {}),
        ("evidence_region", {}),
        ("uncertainty", []),
        ("alternate_labels", []),
        ("metadata", {}),
    ):
        item[key] = _load_json(item.get(key), default)
    return item


def _state(candidate: dict[str, Any] | None) -> str | None:
    return json.dumps(candidate, sort_keys=True, default=str) if candidate is not None else None


def _write_event(
    db: sqlite3.Connection,
    *,
    visual_candidate_id: str,
    operation: str,
    actor: str,
    reason: str,
    previous: dict[str, Any] | None,
    resulting: dict[str, Any],
    timestamp: str,
) -> None:
    db.execute(
        """
        INSERT INTO visual_analysis_candidate_events
        (visual_candidate_id, operation, actor, reason, timestamp, previous_state, resulting_state)
        VALUES (?,?,?,?,?,?,?)
        """,
        (visual_candidate_id, operation, actor, reason, timestamp, _state(previous), _state(resulting)),
    )


def _insert_candidate(db: sqlite3.Connection, candidate: dict[str, Any]) -> None:
    db.execute(
        """
        INSERT INTO visual_analysis_candidates (
            visual_candidate_id, source_video_candidate_id, source_frame_reference,
            source_frame_hash, frame_timestamp, proposed_label, normalized_label,
            broad_category, confidence, evidence_region, source_model,
            model_version, analysis_method_version, processing_timestamp,
            uncertainty, alternate_labels, privacy_scope, status, reviewed_by,
            reviewed_at, review_reason, corrected_label, approved_observation_id,
            metadata
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            candidate["visual_candidate_id"],
            candidate["source_video_candidate_id"],
            _json(candidate["source_frame_reference"]),
            candidate["source_frame_hash"],
            float(candidate["frame_timestamp"]),
            candidate["proposed_label"],
            candidate["normalized_label"],
            candidate.get("broad_category"),
            float(candidate.get("confidence", 0.0)),
            _json(candidate.get("evidence_region", {})),
            candidate["source_model"],
            candidate["model_version"],
            candidate["analysis_method_version"],
            candidate["processing_timestamp"],
            _json(candidate.get("uncertainty", [])),
            _json(candidate.get("alternate_labels", [])),
            candidate.get("privacy_scope", "owner_private"),
            candidate["status"],
            candidate.get("reviewed_by"),
            candidate.get("reviewed_at"),
            candidate.get("review_reason"),
            candidate.get("corrected_label"),
            candidate.get("approved_observation_id"),
            _json(candidate.get("metadata", {})),
        ),
    )


def _update_candidate(db: sqlite3.Connection, candidate: dict[str, Any]) -> None:
    db.execute(
        """
        UPDATE visual_analysis_candidates SET
            status=?, reviewed_by=?, reviewed_at=?, review_reason=?,
            corrected_label=?, approved_observation_id=?, metadata=?
        WHERE visual_candidate_id=?
        """,
        (
            candidate["status"],
            candidate.get("reviewed_by"),
            candidate.get("reviewed_at"),
            candidate.get("review_reason"),
            candidate.get("corrected_label"),
            candidate.get("approved_observation_id"),
            _json(candidate.get("metadata", {})),
            candidate["visual_candidate_id"],
        ),
    )


def get_visual_candidate(visual_candidate_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as db:
        row = db.execute(
            "SELECT * FROM visual_analysis_candidates WHERE visual_candidate_id=?",
            (visual_candidate_id,),
        ).fetchone()
    return _row_to_candidate(row)


def list_visual_candidates(
    *,
    video_candidate_id: str | None = None,
    status: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if video_candidate_id:
        clauses.append("source_video_candidate_id=?")
        params.append(video_candidate_id)
    if status:
        clauses.append("status=?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(db_path) as db:
        rows = db.execute(
            f"SELECT * FROM visual_analysis_candidates {where} ORDER BY frame_timestamp ASC, proposed_label ASC",
            params,
        ).fetchall()
    return [_row_to_candidate(row) for row in rows]


def list_events(visual_candidate_id: str, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT * FROM visual_analysis_candidate_events WHERE visual_candidate_id=? ORDER BY event_id ASC",
            (visual_candidate_id,),
        ).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        event["previous_state"] = _load_json(event.get("previous_state"), None)
        event["resulting_state"] = _load_json(event.get("resulting_state"), {})
        events.append(event)
    return events


def verify_frame_readable(frame: dict[str, Any]) -> dict[str, Any]:
    path = Path(frame.get("path", ""))
    expected_hash = frame.get("sha256")
    if not path.exists() or not path.is_file():
        raise VisualAnalysisError(f"frame evidence missing: {frame.get('frame_id')}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_hash and digest != expected_hash:
        raise VisualAnalysisError(f"frame hash mismatch: {frame.get('frame_id')}")
    try:
        with Image.open(path) as image:
            image.load()
            return {
                "path": str(path),
                "sha256": digest,
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "format": image.format,
            }
    except Exception as exc:
        raise VisualAnalysisError(f"frame is not readable: {frame.get('frame_id')}: {exc}") from exc


def analyze_frame_pixels(frame: dict[str, Any], frame_info: dict[str, Any], *, method: str) -> list[dict[str, Any]]:
    """Return tentative labels from a real pixel-inspection method.

    The default method deliberately returns no labels because no usable local
    vision model was found during the Day 9 audit. Tests may inject a fixture
    analyzer, but production code must not invent labels from filenames or chat
    context.
    """
    if method != NO_MODEL_METHOD:
        raise VisualAnalysisError(f"unsupported local visual analysis method: {method}")
    return []


def _candidate_from_proposal(
    *,
    video_candidate_id: str,
    frame: dict[str, Any],
    frame_info: dict[str, Any],
    proposal: dict[str, Any],
    privacy_scope: str,
    method: str,
    ts: str,
) -> dict[str, Any]:
    label = str(proposal["proposed_label"]).strip()
    if not label:
        raise VisualAnalysisError("visual proposal missing proposed_label")
    normalized = normalize_label(label)
    return {
        "visual_candidate_id": visual_candidate_id_for(video_candidate_id, frame_info["sha256"], normalized, method),
        "source_video_candidate_id": video_candidate_id,
        "source_frame_reference": {
            "frame_id": frame.get("frame_id"),
            "timestamp_seconds": frame.get("timestamp_seconds"),
            "sha256": frame_info["sha256"],
            "path": frame_info["path"],
        },
        "source_frame_hash": frame_info["sha256"],
        "frame_timestamp": float(frame.get("timestamp_seconds", 0.0)),
        "proposed_label": label,
        "normalized_label": normalized,
        "broad_category": proposal.get("broad_category", "unknown"),
        "confidence": float(proposal.get("confidence", 0.0)),
        "evidence_region": proposal.get("evidence_region") or {},
        "source_model": proposal.get("source_model", method),
        "model_version": proposal.get("model_version", method),
        "analysis_method_version": method,
        "processing_timestamp": ts,
        "uncertainty": list(proposal.get("uncertainty") or []),
        "alternate_labels": list(proposal.get("alternate_labels") or []),
        "privacy_scope": privacy_scope,
        "status": "pending_review",
        "reviewed_by": None,
        "reviewed_at": None,
        "review_reason": None,
        "corrected_label": None,
        "approved_observation_id": None,
        "metadata": {
            "frame_width": frame_info["width"],
            "frame_height": frame_info["height"],
            "frame_format": frame_info["format"],
            "analysis_scope": "existing_evidence_frame_only",
            "face_recognition_performed": False,
            "source_used": "image_pixels",
        },
    }


def analyze_video_candidate(
    video_candidate_id: str,
    *,
    db_path: str | Path | None = None,
    video_db_path: str | Path | None = None,
    method: str = NO_MODEL_METHOD,
    actor: str = "manual_reviewer",
) -> dict[str, Any]:
    video_candidate = get_video_candidate(video_candidate_id, db_path=video_db_path)
    if not video_candidate:
        raise VisualAnalysisError(f"video candidate not found: {video_candidate_id}")
    frames = list(video_candidate.get("evidence_frame_references") or [])
    if not frames:
        raise VisualAnalysisError("video candidate has no evidence frames")
    ts = utcnow()
    created: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    readable_frames: list[dict[str, Any]] = []
    with connect(db_path) as db:
        for frame in frames:
            frame_info = verify_frame_readable(frame)
            readable_frames.append({
                "frame_id": frame.get("frame_id"),
                "timestamp_seconds": frame.get("timestamp_seconds"),
                "sha256": frame_info["sha256"],
                "width": frame_info["width"],
                "height": frame_info["height"],
            })
            proposals = analyze_frame_pixels(frame, frame_info, method=method)
            seen_labels: set[str] = set()
            for proposal in proposals:
                if proposal.get("person_identification") or proposal.get("face_recognition_performed"):
                    raise VisualAnalysisError("person identification and face recognition are not allowed")
                candidate = _candidate_from_proposal(
                    video_candidate_id=video_candidate_id,
                    frame=frame,
                    frame_info=frame_info,
                    proposal=proposal,
                    privacy_scope=video_candidate.get("privacy_scope", "owner_private"),
                    method=method,
                    ts=ts,
                )
                if candidate["normalized_label"] in seen_labels:
                    continue
                seen_labels.add(candidate["normalized_label"])
                existing = db.execute(
                    "SELECT * FROM visual_analysis_candidates WHERE visual_candidate_id=?",
                    (candidate["visual_candidate_id"],),
                ).fetchone()
                if existing:
                    duplicates.append(_row_to_candidate(existing))
                    continue
                _insert_candidate(db, candidate)
                _write_event(
                    db,
                    visual_candidate_id=candidate["visual_candidate_id"],
                    operation="create_visual_candidate",
                    actor=actor,
                    reason="bounded local visual analysis of evidence frame",
                    previous=None,
                    resulting=candidate,
                    timestamp=ts,
                )
                created.append(candidate)
        db.commit()
    missing = None
    if method == NO_MODEL_METHOD:
        missing = {
            "missing_capability": "local_vision_model_or_object_detector",
            "reason": "No installed local model capable of image/object analysis was found; labels were not invented.",
            "required_interface": "local image-to-label model returning label, confidence, uncertainty, alternatives, and optional bounding box",
        }
    return {
        "ok": True,
        "source_video_candidate_id": video_candidate_id,
        "method": method,
        "frames_checked": readable_frames,
        "created_count": len(created),
        "duplicate_count": len(duplicates),
        "candidates": created,
        "duplicates": duplicates,
        "consolidated": consolidate_candidates(video_candidate_id, db_path=db_path),
        "missing_capability": missing,
    }


def _review(
    visual_candidate_id: str,
    *,
    status: str,
    reviewer: str,
    reason: str,
    corrected_label: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if status not in {"approved", "corrected", "rejected"}:
        raise VisualAnalysisError(f"unsupported review status: {status}")
    if not reviewer:
        raise VisualAnalysisError("reviewer is required")
    if not reason:
        raise VisualAnalysisError("review reason is required")
    ts = utcnow()
    with connect(db_path) as db:
        row = db.execute(
            "SELECT * FROM visual_analysis_candidates WHERE visual_candidate_id=?",
            (visual_candidate_id,),
        ).fetchone()
        candidate = _row_to_candidate(row)
        if not candidate:
            raise VisualAnalysisError(f"visual candidate not found: {visual_candidate_id}")
        if candidate["status"] == "rejected" and status == "approved":
            raise VisualAnalysisError("rejected candidates cannot be silently approved")
        if candidate["status"] in {"approved", "corrected"} and status == "rejected":
            raise VisualAnalysisError("reviewed candidates cannot be silently rejected")
        previous = dict(candidate)
        candidate.update({
            "status": status,
            "reviewed_by": reviewer,
            "reviewed_at": ts,
            "review_reason": reason,
            "corrected_label": corrected_label if status == "corrected" else candidate.get("corrected_label"),
        })
        _update_candidate(db, candidate)
        _write_event(
            db,
            visual_candidate_id=visual_candidate_id,
            operation=f"{status}_visual_candidate",
            actor=reviewer,
            reason=reason,
            previous=previous,
            resulting=candidate,
            timestamp=ts,
        )
        db.commit()
    return get_visual_candidate(visual_candidate_id, db_path=db_path)


def approve_candidate(visual_candidate_id: str, *, reviewer: str, reason: str, db_path: str | Path | None = None) -> dict[str, Any]:
    return _review(visual_candidate_id, status="approved", reviewer=reviewer, reason=reason, db_path=db_path)


def correct_candidate(
    visual_candidate_id: str,
    *,
    label: str,
    reviewer: str,
    reason: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if not label:
        raise VisualAnalysisError("corrected label is required")
    return _review(visual_candidate_id, status="corrected", reviewer=reviewer, reason=reason, corrected_label=label, db_path=db_path)


def reject_candidate(visual_candidate_id: str, *, reviewer: str, reason: str, db_path: str | Path | None = None) -> dict[str, Any]:
    return _review(visual_candidate_id, status="rejected", reviewer=reviewer, reason=reason, db_path=db_path)


def consolidate_candidates(video_candidate_id: str, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    candidates = list_visual_candidates(video_candidate_id=video_candidate_id, db_path=db_path)
    groups: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        label = normalize_label(candidate.get("corrected_label") or candidate["proposed_label"])
        group = groups.setdefault(label, {
            "label": label,
            "status_counts": {},
            "supporting_timestamps": [],
            "supporting_candidate_ids": [],
            "supporting_frame_hashes": [],
            "uncertainty": [],
            "alternate_labels": [],
        })
        group["status_counts"][candidate["status"]] = group["status_counts"].get(candidate["status"], 0) + 1
        group["supporting_timestamps"].append(candidate["frame_timestamp"])
        group["supporting_candidate_ids"].append(candidate["visual_candidate_id"])
        group["supporting_frame_hashes"].append(candidate["source_frame_hash"])
        group["uncertainty"].extend(candidate.get("uncertainty") or [])
        group["alternate_labels"].extend(candidate.get("alternate_labels") or [])
    for group in groups.values():
        group["supporting_timestamps"] = sorted(set(group["supporting_timestamps"]))
        group["supporting_frame_hashes"] = sorted(set(group["supporting_frame_hashes"]))
        group["uncertainty"] = sorted(set(group["uncertainty"]))
        group["alternate_labels"] = sorted(set(group["alternate_labels"]))
    return sorted(groups.values(), key=lambda item: item["label"])


def review_summary(video_candidate_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    candidates = list_visual_candidates(video_candidate_id=video_candidate_id, db_path=db_path)
    by_timestamp: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        key = f"{candidate['frame_timestamp']:.3f}s"
        by_timestamp.setdefault(key, []).append({
            "visual_candidate_id": candidate["visual_candidate_id"],
            "proposed_label": candidate["proposed_label"],
            "confidence": candidate["confidence"],
            "alternate_labels": candidate.get("alternate_labels", []),
            "uncertainty": candidate.get("uncertainty", []),
            "source_frame_hash": candidate["source_frame_hash"],
            "status": candidate["status"],
        })
    return {
        "source_video_candidate_id": video_candidate_id,
        "by_timestamp": by_timestamp,
        "consolidated": consolidate_candidates(video_candidate_id, db_path=db_path),
    }


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--video-db", type=Path)
    sub = parser.add_subparsers(dest="cmd", required=True)

    analyze = sub.add_parser("analyze")
    analyze.add_argument("--video-candidate-id", required=True)
    analyze.add_argument("--method", default=NO_MODEL_METHOD)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--video-candidate-id")
    list_cmd.add_argument("--status")

    show = sub.add_parser("show")
    show.add_argument("--candidate-id", required=True)

    approve = sub.add_parser("approve")
    approve.add_argument("--candidate-id", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--reason", required=True)

    correct = sub.add_parser("correct")
    correct.add_argument("--candidate-id", required=True)
    correct.add_argument("--label", required=True)
    correct.add_argument("--reviewer", required=True)
    correct.add_argument("--reason", required=True)

    reject = sub.add_parser("reject")
    reject.add_argument("--candidate-id", required=True)
    reject.add_argument("--reviewer", required=True)
    reject.add_argument("--reason", required=True)

    events = sub.add_parser("events")
    events.add_argument("--candidate-id", required=True)

    summary = sub.add_parser("summary")
    summary.add_argument("--video-candidate-id", required=True)

    args = parser.parse_args()
    if args.cmd == "analyze":
        _print(analyze_video_candidate(args.video_candidate_id, db_path=args.db, video_db_path=args.video_db, method=args.method))
    elif args.cmd == "list":
        _print(list_visual_candidates(video_candidate_id=args.video_candidate_id, status=args.status, db_path=args.db))
    elif args.cmd == "show":
        _print(get_visual_candidate(args.candidate_id, db_path=args.db) or {})
    elif args.cmd == "approve":
        _print(approve_candidate(args.candidate_id, reviewer=args.reviewer, reason=args.reason, db_path=args.db))
    elif args.cmd == "correct":
        _print(correct_candidate(args.candidate_id, label=args.label, reviewer=args.reviewer, reason=args.reason, db_path=args.db))
    elif args.cmd == "reject":
        _print(reject_candidate(args.candidate_id, reviewer=args.reviewer, reason=args.reason, db_path=args.db))
    elif args.cmd == "events":
        _print(list_events(args.candidate_id, db_path=args.db))
    elif args.cmd == "summary":
        _print(review_summary(args.video_candidate_id, db_path=args.db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
