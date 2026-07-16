#!/usr/bin/env python3
"""Reviewable local-video observation candidates for Echo Asset System.

This module is intentionally pre-observation. It extracts bounded evidence
from a local video and stores reviewable candidates. Only an explicit approval
routes confirmed facts through ObservationManager into permanent asset history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets.asset_database import AssetDatabase
from assets.observation_manager import ObservationManager

DEFAULT_DB_PATH = BASE / "memory" / "video_observation_candidates.sqlite"
DEFAULT_EVIDENCE_DIR = BASE / "memory" / "video_observation_candidates"
ALLOWED_STATUSES = {"pending_review", "approved", "rejected", "superseded"}


class VideoCandidateError(RuntimeError):
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_id_for(source_hash: str, asset_id: str | None, transcript_reference: str | None) -> str:
    digest = hashlib.sha256(f"{source_hash}|{asset_id or ''}|{transcript_reference or ''}".encode()).hexdigest()[:16]
    return f"video-candidate-{digest}"


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
        CREATE TABLE IF NOT EXISTS video_observation_candidates (
            candidate_id TEXT PRIMARY KEY,
            source_video_path TEXT NOT NULL,
            source_private_reference TEXT,
            source_file_hash TEXT NOT NULL,
            asset_id TEXT,
            start_timestamp REAL NOT NULL,
            end_timestamp REAL NOT NULL,
            evidence_frame_references TEXT NOT NULL DEFAULT '[]',
            transcript_reference TEXT,
            raw_description TEXT NOT NULL,
            extracted_candidate_facts TEXT NOT NULL DEFAULT '{}',
            inferred_candidate_facts TEXT NOT NULL DEFAULT '{}',
            confidence REAL NOT NULL DEFAULT 0.0,
            uncertainty TEXT NOT NULL DEFAULT '[]',
            processing_method TEXT NOT NULL,
            privacy_scope TEXT NOT NULL DEFAULT 'owner_private',
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by TEXT,
            rejection_reason TEXT,
            approved_observation_id INTEGER,
            approved_observation_payload TEXT NOT NULL DEFAULT '{}',
            metadata TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS video_observation_candidate_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            actor TEXT NOT NULL,
            reason TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            previous_state TEXT,
            resulting_state TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_video_candidates_status ON video_observation_candidates(status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_video_candidates_hash ON video_observation_candidates(source_file_hash)")
    db.commit()


def _row_to_candidate(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for key, default in (
        ("evidence_frame_references", []),
        ("extracted_candidate_facts", {}),
        ("inferred_candidate_facts", {}),
        ("uncertainty", []),
        ("approved_observation_payload", {}),
        ("metadata", {}),
    ):
        item[key] = _load_json(item.get(key), default)
    return item


def _state(candidate: dict[str, Any] | None) -> str | None:
    return json.dumps(candidate, sort_keys=True, default=str) if candidate is not None else None


def _write_event(
    db: sqlite3.Connection,
    *,
    candidate_id: str,
    operation: str,
    actor: str,
    reason: str,
    previous: dict[str, Any] | None,
    resulting: dict[str, Any],
    timestamp: str,
) -> None:
    db.execute(
        """
        INSERT INTO video_observation_candidate_events
        (candidate_id, operation, actor, reason, timestamp, previous_state, resulting_state)
        VALUES (?,?,?,?,?,?,?)
        """,
        (candidate_id, operation, actor, reason, timestamp, _state(previous), _state(resulting)),
    )


def _insert_candidate(db: sqlite3.Connection, candidate: dict[str, Any]) -> None:
    db.execute(
        """
        INSERT INTO video_observation_candidates (
            candidate_id, source_video_path, source_private_reference,
            source_file_hash, asset_id, start_timestamp, end_timestamp,
            evidence_frame_references, transcript_reference, raw_description,
            extracted_candidate_facts, inferred_candidate_facts, confidence,
            uncertainty, processing_method, privacy_scope, status, created_at,
            reviewed_at, reviewed_by, rejection_reason, approved_observation_id,
            approved_observation_payload, metadata
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            candidate["candidate_id"],
            candidate["source_video_path"],
            candidate.get("source_private_reference"),
            candidate["source_file_hash"],
            candidate.get("asset_id"),
            float(candidate.get("start_timestamp", 0.0)),
            float(candidate.get("end_timestamp", 0.0)),
            _json(candidate.get("evidence_frame_references", [])),
            candidate.get("transcript_reference"),
            candidate["raw_description"],
            _json(candidate.get("extracted_candidate_facts", {})),
            _json(candidate.get("inferred_candidate_facts", {})),
            float(candidate.get("confidence", 0.0)),
            _json(candidate.get("uncertainty", [])),
            candidate["processing_method"],
            candidate.get("privacy_scope", "owner_private"),
            candidate["status"],
            candidate["created_at"],
            candidate.get("reviewed_at"),
            candidate.get("reviewed_by"),
            candidate.get("rejection_reason"),
            candidate.get("approved_observation_id"),
            _json(candidate.get("approved_observation_payload", {})),
            _json(candidate.get("metadata", {})),
        ),
    )


def _update_candidate(db: sqlite3.Connection, candidate: dict[str, Any]) -> None:
    db.execute(
        """
        UPDATE video_observation_candidates SET
            asset_id=?, evidence_frame_references=?, raw_description=?,
            extracted_candidate_facts=?, inferred_candidate_facts=?, confidence=?,
            uncertainty=?, processing_method=?, privacy_scope=?, status=?,
            reviewed_at=?, reviewed_by=?, rejection_reason=?,
            approved_observation_id=?, approved_observation_payload=?, metadata=?
        WHERE candidate_id=?
        """,
        (
            candidate.get("asset_id"),
            _json(candidate.get("evidence_frame_references", [])),
            candidate["raw_description"],
            _json(candidate.get("extracted_candidate_facts", {})),
            _json(candidate.get("inferred_candidate_facts", {})),
            float(candidate.get("confidence", 0.0)),
            _json(candidate.get("uncertainty", [])),
            candidate["processing_method"],
            candidate.get("privacy_scope", "owner_private"),
            candidate["status"],
            candidate.get("reviewed_at"),
            candidate.get("reviewed_by"),
            candidate.get("rejection_reason"),
            candidate.get("approved_observation_id"),
            _json(candidate.get("approved_observation_payload", {})),
            _json(candidate.get("metadata", {})),
            candidate["candidate_id"],
        ),
    )


def get_candidate(candidate_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as db:
        return _row_to_candidate(
            db.execute("SELECT * FROM video_observation_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        )


def list_candidates(status: str | None = None, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as db:
        if status:
            rows = db.execute(
                "SELECT * FROM video_observation_candidates WHERE status=? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM video_observation_candidates ORDER BY created_at DESC").fetchall()
    return [_row_to_candidate(row) for row in rows]


def list_events(candidate_id: str, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT * FROM video_observation_candidate_events WHERE candidate_id=? ORDER BY event_id ASC",
            (candidate_id,),
        ).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        event["previous_state"] = _load_json(event.get("previous_state"), None)
        event["resulting_state"] = _load_json(event.get("resulting_state"), {})
        events.append(event)
    return events


def _run_json(cmd: list[str], *, timeout: int = 20) -> dict[str, Any]:
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
    return json.loads(proc.stdout or "{}")


def inspect_video_metadata(video_path: Path) -> dict[str, Any]:
    if not shutil.which("ffprobe"):
        raise VideoCandidateError("ffprobe is required for local video metadata inspection")
    return _run_json([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(video_path)
    ])


def video_duration_seconds(metadata: dict[str, Any]) -> float:
    duration = (metadata.get("format") or {}).get("duration")
    if duration is not None:
        try:
            return max(0.0, float(duration))
        except (TypeError, ValueError):
            pass
    for stream in metadata.get("streams") or []:
        if stream.get("duration") is not None:
            try:
                return max(0.0, float(stream["duration"]))
            except (TypeError, ValueError):
                continue
    return 0.0


def _frame_times(duration: float, max_frames: int) -> list[float]:
    if max_frames <= 0 or duration <= 0:
        return []
    count = min(max_frames, max(1, int(duration) if duration < max_frames else max_frames))
    if count == 1:
        return [round(duration / 2.0, 3)]
    step = duration / (count + 1)
    return [round(step * (idx + 1), 3) for idx in range(count)]


def extract_representative_frames(
    video_path: Path,
    *,
    output_dir: Path,
    duration_seconds: float,
    max_frames: int = 5,
) -> list[dict[str, Any]]:
    if not shutil.which("ffmpeg"):
        raise VideoCandidateError("ffmpeg is required for local evidence frame extraction")
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    for index, timestamp in enumerate(_frame_times(duration_seconds, max_frames), start=1):
        frame_path = output_dir / f"frame_{index:03d}_{int(timestamp * 1000):08d}ms.jpg"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{timestamp:.3f}", "-i", str(video_path), "-frames:v", "1", str(frame_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        frames.append({
            "frame_id": f"frame-{index:03d}",
            "timestamp_seconds": timestamp,
            "path": str(frame_path),
            "sha256": sha256_file(frame_path),
            "bytes": frame_path.stat().st_size,
        })
    return frames


def ingest_video(
    video_path: str | Path,
    *,
    asset_id: str | None = None,
    transcript_reference: str | None = None,
    privacy_scope: str = "owner_private",
    max_frames: int = 5,
    db_path: str | Path | None = None,
    evidence_dir: str | Path | None = None,
    actor: str = "manual_reviewer",
) -> dict[str, Any]:
    path = Path(video_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise VideoCandidateError(f"video file not found: {path}")
    source_hash = sha256_file(path)
    candidate_id = candidate_id_for(source_hash, asset_id, transcript_reference)
    ts = utcnow()
    with connect(db_path) as db:
        existing = _row_to_candidate(
            db.execute("SELECT * FROM video_observation_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        )
        if existing:
            return {"ok": True, "duplicate": True, "candidate": existing}
        metadata = inspect_video_metadata(path)
        duration = video_duration_seconds(metadata)
        frame_dir = Path(evidence_dir or DEFAULT_EVIDENCE_DIR) / candidate_id / "frames"
        frames = extract_representative_frames(path, output_dir=frame_dir, duration_seconds=duration, max_frames=max_frames)
        candidate = {
            "candidate_id": candidate_id,
            "source_video_path": str(path),
            "source_private_reference": str(path),
            "source_file_hash": source_hash,
            "asset_id": asset_id,
            "start_timestamp": 0.0,
            "end_timestamp": duration,
            "evidence_frame_references": frames,
            "transcript_reference": transcript_reference,
            "raw_description": (
                "Frame-backed local video review candidate. No visual facts were inferred automatically; "
                "A human reviewer must review evidence frames and confirm facts before asset history is written."
            ),
            "extracted_candidate_facts": {
                "media_duration_seconds": duration,
                "evidence_frame_count": len(frames),
                "source_file_hash": source_hash,
                "transcript_supplied": bool(transcript_reference),
            },
            "inferred_candidate_facts": {},
            "confidence": 0.0,
            "uncertainty": [
                "No computer vision analysis was performed.",
                "Evidence frames require human review before any asset observation is created.",
            ],
            "processing_method": "local_ffprobe_ffmpeg_frame_sampling_v1",
            "privacy_scope": privacy_scope,
            "status": "pending_review",
            "created_at": ts,
            "reviewed_at": None,
            "reviewed_by": None,
            "rejection_reason": None,
            "approved_observation_id": None,
            "approved_observation_payload": {},
            "metadata": {
                "ffmpeg": shutil.which("ffmpeg"),
                "ffprobe": shutil.which("ffprobe"),
                "max_frames": max_frames,
                "video_streams": [
                    {
                        "codec_type": stream.get("codec_type"),
                        "codec_name": stream.get("codec_name"),
                        "width": stream.get("width"),
                        "height": stream.get("height"),
                        "r_frame_rate": stream.get("r_frame_rate"),
                    }
                    for stream in metadata.get("streams", [])
                    if stream.get("codec_type") in {"video", "audio", "subtitle"}
                ],
            },
        }
        _insert_candidate(db, candidate)
        stored = _row_to_candidate(
            db.execute("SELECT * FROM video_observation_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        )
        _write_event(
            db,
            candidate_id=candidate_id,
            operation="create_candidate",
            actor=actor,
            reason="bounded local video evidence extraction",
            previous=None,
            resulting=stored or candidate,
            timestamp=ts,
        )
        db.commit()
    return {"ok": True, "duplicate": False, "candidate": get_candidate(candidate_id, db_path=db_path)}


def reject_candidate(
    candidate_id: str,
    *,
    reviewer: str,
    reason: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if not reviewer:
        raise VideoCandidateError("reviewer is required")
    if not reason:
        raise VideoCandidateError("rejection reason is required")
    ts = utcnow()
    with connect(db_path) as db:
        candidate = _row_to_candidate(
            db.execute("SELECT * FROM video_observation_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        )
        if not candidate:
            raise VideoCandidateError(f"candidate not found: {candidate_id}")
        if candidate["status"] == "approved":
            raise VideoCandidateError("approved candidates cannot be rejected")
        previous = dict(candidate)
        candidate.update({"status": "rejected", "reviewed_at": ts, "reviewed_by": reviewer, "rejection_reason": reason})
        _update_candidate(db, candidate)
        _write_event(
            db,
            candidate_id=candidate_id,
            operation="reject_candidate",
            actor=reviewer,
            reason=reason,
            previous=previous,
            resulting=candidate,
            timestamp=ts,
        )
        db.commit()
    return get_candidate(candidate_id, db_path=db_path)


def approve_candidate(
    candidate_id: str,
    *,
    reviewer: str,
    reason: str,
    confirmed_facts: dict[str, Any],
    asset_id: str | None = None,
    db_path: str | Path | None = None,
    asset_db_path: str | Path | None = None,
    observations_dir: str | Path | None = None,
) -> dict[str, Any]:
    if not reviewer:
        raise VideoCandidateError("reviewer is required")
    if not reason:
        raise VideoCandidateError("approval reason is required")
    if not confirmed_facts:
        raise VideoCandidateError("confirmed_facts are required for approval")
    ts = utcnow()
    with connect(db_path) as db:
        candidate = _row_to_candidate(
            db.execute("SELECT * FROM video_observation_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        )
        if not candidate:
            raise VideoCandidateError(f"candidate not found: {candidate_id}")
        if candidate["status"] == "approved":
            return {"candidate": candidate, "observation_result": {"duplicate": True, "observation_id": candidate.get("approved_observation_id")}}
        if candidate["status"] == "rejected":
            raise VideoCandidateError("rejected candidates cannot be approved without an audited reopen operation")
        if candidate["status"] != "pending_review":
            raise VideoCandidateError(f"candidate cannot be approved from state: {candidate['status']}")
        target_asset = asset_id or candidate.get("asset_id")
        if not target_asset:
            raise VideoCandidateError("asset_id is required when approving a candidate")
        payload = {
            "schema": "echo.asset_observation",
            "schema_version": 1,
            "kind": "video_review",
            "asset_id": target_asset,
            "timestamp": ts,
            "source": "video_review",
            "observer": reviewer,
            "summary": f"Approved video observation candidate {candidate_id}",
            "raw_text": reason,
            "raw_input_reference": candidate_id,
            "processing_method": "reviewable_video_observation_candidates_v1",
            "review_status": "reviewed",
            "confidence": 1.0,
            "tags": ["asset_intelligence", "video_review"],
            "extracted_facts": confirmed_facts,
            "inferred_facts": {},
            "uncertainty": candidate.get("uncertainty", []),
            "recommended_next_action": "Review asset history and decide whether a separate approved task proposal is needed.",
            "provenance": {
                "candidate_id": candidate_id,
                "source_file_hash": candidate["source_file_hash"],
                "evidence_frame_references": candidate.get("evidence_frame_references", []),
                "transcript_reference": candidate.get("transcript_reference"),
                "reviewer": reviewer,
                "approval_reason": reason,
                "privacy_scope": candidate.get("privacy_scope"),
            },
        }
        manager = ObservationManager(
            AssetDatabase(Path(asset_db_path)) if asset_db_path else None,
            observations_dir=Path(observations_dir) if observations_dir else None,
        )
        result = manager.ingest(payload)
        previous = dict(candidate)
        candidate.update({
            "asset_id": target_asset,
            "status": "approved",
            "reviewed_at": ts,
            "reviewed_by": reviewer,
            "approved_observation_id": result.get("observation_id"),
            "approved_observation_payload": payload,
        })
        _update_candidate(db, candidate)
        _write_event(
            db,
            candidate_id=candidate_id,
            operation="approve_candidate",
            actor=reviewer,
            reason=reason,
            previous=previous,
            resulting=candidate,
            timestamp=ts,
        )
        db.commit()
    return {"candidate": get_candidate(candidate_id, db_path=db_path), "observation_result": result}


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _self_test() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "assets.video_observation_candidates",
        "storage": str(DEFAULT_DB_PATH),
        "evidence_dir": str(DEFAULT_EVIDENCE_DIR),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "statuses": sorted(ALLOWED_STATUSES),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--asset-db", type=Path)
    parser.add_argument("--observations-dir", type=Path)
    sub = parser.add_subparsers(dest="cmd", required=True)

    ingest = sub.add_parser("ingest")
    ingest.add_argument("--video", required=True)
    ingest.add_argument("--asset-id")
    ingest.add_argument("--transcript-reference")
    ingest.add_argument("--privacy-scope", default="owner_private")
    ingest.add_argument("--max-frames", type=int, default=5)

    show = sub.add_parser("show")
    show.add_argument("--candidate-id", required=True)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--status")

    approve = sub.add_parser("approve")
    approve.add_argument("--candidate-id", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--reason", required=True)
    approve.add_argument("--asset-id")
    approve.add_argument("--confirmed-facts-json", required=True)

    reject = sub.add_parser("reject")
    reject.add_argument("--candidate-id", required=True)
    reject.add_argument("--reviewer", required=True)
    reject.add_argument("--reason", required=True)

    events = sub.add_parser("events")
    events.add_argument("--candidate-id", required=True)
    sub.add_parser("self-test")

    args = parser.parse_args()
    if args.cmd == "ingest":
        _print(ingest_video(
            args.video,
            asset_id=args.asset_id,
            transcript_reference=args.transcript_reference,
            privacy_scope=args.privacy_scope,
            max_frames=args.max_frames,
            db_path=args.db,
            evidence_dir=args.evidence_dir,
        ))
    elif args.cmd == "show":
        _print(get_candidate(args.candidate_id, db_path=args.db) or {})
    elif args.cmd == "list":
        _print(list_candidates(args.status, db_path=args.db))
    elif args.cmd == "approve":
        _print(approve_candidate(
            args.candidate_id,
            reviewer=args.reviewer,
            reason=args.reason,
            confirmed_facts=json.loads(args.confirmed_facts_json),
            asset_id=args.asset_id,
            db_path=args.db,
            asset_db_path=args.asset_db,
            observations_dir=args.observations_dir,
        ))
    elif args.cmd == "reject":
        _print(reject_candidate(args.candidate_id, reviewer=args.reviewer, reason=args.reason, db_path=args.db))
    elif args.cmd == "events":
        _print(list_events(args.candidate_id, db_path=args.db))
    elif args.cmd == "self-test":
        _print(_self_test())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
