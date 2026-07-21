from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from assets import workspace_state_candidates as wsc
from assets.asset_database import AssetDatabase


def _insert_visual_candidate(
    db: sqlite3.Connection,
    *,
    cid: str,
    video_id: str,
    label: str,
    timestamp: float,
    status: str = "corrected",
) -> None:
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
            cid,
            video_id,
            "{}",
            f"hash-{timestamp}-{cid}",
            timestamp,
            label,
            wsc.normalize_text(label),
            "fixture",
            0.8,
            "{}",
            "fixture_model",
            "fixture-v1",
            "fixture_method",
            "2026-01-01T00:00:00+00:00",
            "[]",
            "[]",
            "owner_private",
            status,
            "FixtureReviewer" if status in {"approved", "corrected"} else None,
            "2026-01-01T00:00:00+00:00" if status in {"approved", "corrected"} else None,
            "fixture review" if status in {"approved", "corrected"} else None,
            label if status == "corrected" else None,
            None,
            "{}",
        ),
    )


def _fixture_visual_db(tmp_path: Path, *, pending: bool = False) -> Path:
    from assets.visual_analysis_candidates import ensure_schema

    path = tmp_path / "visual.sqlite"
    con = sqlite3.connect(path)
    ensure_schema(con)
    video_id = "video-candidate-fixture"
    fixture_rows = [
        ("vc-desk-1", "desk/work surface", 1.0),
        ("vc-desk-2", "desk/work surface", 2.0),
        ("vc-keyboard-1", "blue-backlit keyboard", 1.0),
        ("vc-keyboard-2", "blue-backlit keyboard", 2.0),
        ("vc-monitor-1", "computer monitor", 1.0),
        ("vc-monitor-2", "computer monitor", 2.0),
        ("vc-controller", "black game controller with red controls", 1.0),
        ("vc-headset", "black over-ear headset with attached microphone", 2.0),
        ("vc-ingot", "small metal ingot or block", 22.336),
        ("vc-cloth", "folded green cloth or towel", 22.336),
        ("vc-case", "black glass-sided computer case with RGB lighting", 37.226),
        ("vc-surface", "black tabletop or shelf surface", 37.226),
        ("vc-container", "small labeled container", 37.226),
        ("vc-striped", "striped cloth or fabric visible through or reflected in glass", 37.226),
    ]
    for cid, label, ts in fixture_rows:
        _insert_visual_candidate(con, cid=cid, video_id=video_id, label=label, timestamp=ts)
    if pending:
        _insert_visual_candidate(con, cid="vc-pending", video_id=video_id, label="fixture pending", timestamp=3.0, status="pending_review")
    con.commit()
    con.close()
    return path


def test_candidate_creation_preserves_provenance_and_time_bounds(tmp_path):
    visual_db = _fixture_visual_db(tmp_path)
    result = wsc.create_snapshot_candidate(
        "video-candidate-fixture",
        db_path=tmp_path / "workspace.sqlite",
        visual_db_path=visual_db,
    )

    assert result["created_relationship_count"] >= 8
    snapshot = result["snapshot"]
    assert snapshot["status"] == "pending_review"
    assert snapshot["start_timestamp"] == 1.0
    assert snapshot["end_timestamp"] == 37.226
    assert "vc-keyboard-1" in snapshot["supporting_visual_candidate_ids"]
    first = result["relationships"][0]
    assert first["supporting_visual_candidate_ids"]
    assert first["supporting_timestamps"]
    assert first["supporting_frame_hashes"]


def test_relationship_support_uses_same_frame_intersection_only():
    subject = [
        {"visual_candidate_id": "subject-a", "frame_timestamp": 1.0, "source_frame_hash": "hash-a"},
        {"visual_candidate_id": "subject-b", "frame_timestamp": 2.0, "source_frame_hash": "hash-b"},
        {"visual_candidate_id": "subject-c", "frame_timestamp": 3.0, "source_frame_hash": "hash-c"},
    ]
    obj = [
        {"visual_candidate_id": "object-b", "frame_timestamp": 2.0, "source_frame_hash": "hash-b"},
        {"visual_candidate_id": "object-c", "frame_timestamp": 3.0, "source_frame_hash": "hash-c"},
        {"visual_candidate_id": "object-d", "frame_timestamp": 4.0, "source_frame_hash": "hash-d"},
    ]

    support = wsc._same_frame_support(subject, obj)
    payload = wsc._support_payload(support)

    assert payload["timestamps"] == [2.0, 3.0]
    assert payload["ids"] == ["object-b", "object-c", "subject-b", "subject-c"]
    assert payload["hashes"] == ["hash-b", "hash-c"]
    assert "subject-a" not in payload["ids"]
    assert "object-d" not in payload["ids"]
    assert "hash-a" not in payload["hashes"]
    assert "hash-d" not in payload["hashes"]


def test_repeated_creation_deduplicates(tmp_path):
    visual_db = _fixture_visual_db(tmp_path)
    db = tmp_path / "workspace.sqlite"

    first = wsc.create_snapshot_candidate("video-candidate-fixture", db_path=db, visual_db_path=visual_db)
    second = wsc.create_snapshot_candidate("video-candidate-fixture", db_path=db, visual_db_path=visual_db)

    assert first["created_relationship_count"] > 0
    assert second["created_relationship_count"] == 0
    assert second["duplicate_relationship_count"] == first["created_relationship_count"]


def test_relationship_correction_and_append_only_history(tmp_path):
    visual_db = _fixture_visual_db(tmp_path)
    db = tmp_path / "workspace.sqlite"
    result = wsc.create_snapshot_candidate("video-candidate-fixture", db_path=db, visual_db_path=visual_db)
    rel = result["relationships"][0]

    corrected = wsc.correct_relationship(
        rel["relationship_candidate_id"],
        relation="near",
        reviewer="FixtureReviewer",
        reason="fixture correction",
        db_path=db,
    )

    assert corrected["proposed_relation"] == rel["proposed_relation"]
    assert corrected["relation"] == "near"
    assert corrected["status"] == "corrected"
    assert [event["operation"] for event in wsc.list_events(rel["relationship_candidate_id"], db_path=db)] == [
        "create_relationship_candidate",
        "corrected_relationship_candidate",
    ]


def test_rejection_prevents_silent_approval(tmp_path):
    visual_db = _fixture_visual_db(tmp_path)
    db = tmp_path / "workspace.sqlite"
    rel = wsc.create_snapshot_candidate("video-candidate-fixture", db_path=db, visual_db_path=visual_db)["relationships"][0]

    wsc.reject_relationship(rel["relationship_candidate_id"], reviewer="FixtureReviewer", reason="not supported", db_path=db)

    with pytest.raises(wsc.WorkspaceStateError, match="cannot be silently approved"):
        wsc.approve_relationship(rel["relationship_candidate_id"], reviewer="FixtureReviewer", reason="approve", db_path=db)


def test_time_bounded_snapshot_status_and_deterministic_summary(tmp_path):
    visual_db = _fixture_visual_db(tmp_path)
    db = tmp_path / "workspace.sqlite"
    result = wsc.create_snapshot_candidate("video-candidate-fixture", db_path=db, visual_db_path=visual_db)
    summary1 = wsc.deterministic_summary(result["snapshot"]["snapshot_id"], db_path=db)
    summary2 = wsc.deterministic_summary(result["snapshot"]["snapshot_id"], db_path=db)

    assert summary1 == summary2
    assert summary1["time_bounds"]["start_timestamp"] == 1.0
    assert summary1["time_bounds"]["end_timestamp"] == 37.226
    assert summary1["boundaries"]["creates_structured_facts"] is False
    assert summary1["boundaries"]["creates_tasks"] is False


def test_no_automatic_permanent_memory_or_task_write(tmp_path):
    visual_db = _fixture_visual_db(tmp_path)
    wsc.create_snapshot_candidate("video-candidate-fixture", db_path=tmp_path / "workspace.sqlite", visual_db_path=visual_db)

    asset_db = AssetDatabase(tmp_path / "assets.sqlite")
    assert asset_db.asset_summary()["observations"] == 0
    assert asset_db.asset_summary()["open_tasks"] == 0
    assert not (tmp_path / "structured_facts.sqlite").exists()


def test_unsupported_relation_is_rejected(tmp_path):
    visual_db = _fixture_visual_db(tmp_path)
    db = tmp_path / "workspace.sqlite"
    rel = wsc.create_snapshot_candidate("video-candidate-fixture", db_path=db, visual_db_path=visual_db)["relationships"][0]

    with pytest.raises(wsc.WorkspaceStateError, match="unsupported relation"):
        wsc.correct_relationship(
            rel["relationship_candidate_id"],
            relation="inside",
            reviewer="FixtureReviewer",
            reason="invalid relation",
            db_path=db,
        )


def test_pending_visual_candidates_block_snapshot(tmp_path):
    visual_db = _fixture_visual_db(tmp_path, pending=True)

    with pytest.raises(wsc.WorkspaceStateError, match="all visual candidates must be reviewed"):
        wsc.create_snapshot_candidate("video-candidate-fixture", db_path=tmp_path / "workspace.sqlite", visual_db_path=visual_db)


def test_self_test_reports_private_storage():
    result = wsc._self_test()

    assert result["ok"] is True
    assert result["writes_permanent_memory"] is False
    assert "on" in result["allowed_relations"]
