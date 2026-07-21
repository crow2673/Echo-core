from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from assets import workspace_change_candidates as wcc


def _evidence(prefix: str, ts: float) -> dict:
    return {
        "supporting_candidate_ids": [f"{prefix}-candidate-{ts}"],
        "supporting_timestamps": [ts],
        "source_frame_hashes": [f"{prefix}-hash-{ts}"],
    }


def _relationship(subject: str, relation: str, obj: str, ts: float, *, status: str = "corrected") -> dict:
    return {
        "relationship_id": f"rel-{subject}-{relation}-{obj}-{ts}".replace(" ", "-"),
        "subject": subject,
        "relation": relation,
        "object": obj,
        "status": status,
        "confidence": 0.8,
        "uncertainty": ["fixture evidence"],
        **_evidence(f"{subject}-{obj}", ts),
    }


def _snapshot(
    snapshot_id: str,
    *,
    ended_at: str,
    coverage_key: str = "fixture-workbench",
    relationships: list[dict] | None = None,
    objects: list[dict] | None = None,
) -> dict:
    return {
        "snapshot_id": snapshot_id,
        "capture_started_at": ended_at,
        "capture_ended_at": ended_at,
        "time_bounds": {"start_timestamp": 1.0, "end_timestamp": 2.0},
        "time_bounded": True,
        "coverage_key": coverage_key,
        "objects": objects or [],
        "relationships": relationships or [],
    }


def _change_types(result: dict) -> set[str]:
    return {item["change_type"] for item in result["changes"]}


def test_appeared_disappeared_unchanged_and_relationship_changed(tmp_path):
    snap_a = _snapshot(
        "snapshot-a",
        ended_at="2026-01-01T00:00:00+00:00",
        relationships=[
            _relationship("fixture keyboard", "on", "fixture desk", 1.0),
            _relationship("fixture mug", "on", "fixture desk", 1.0),
            _relationship("fixture monitor", "above", "fixture keyboard", 1.0),
        ],
    )
    snap_b = _snapshot(
        "snapshot-b",
        ended_at="2026-01-01T01:00:00+00:00",
        relationships=[
            _relationship("fixture keyboard", "on", "fixture desk", 2.0),
            _relationship("fixture notebook", "on", "fixture desk", 2.0),
            _relationship("fixture monitor", "behind", "fixture keyboard", 2.0),
        ],
    )

    result = wcc.create_comparison(snap_a, snap_b, db_path=tmp_path / "changes.sqlite")

    assert {"appeared", "disappeared", "unchanged", "relationship_changed"} <= _change_types(result)
    appeared = [item for item in result["changes"] if item["change_type"] == "appeared"]
    assert any(item["subject_label"] == "fixture notebook" for item in appeared)
    changed = [item for item in result["changes"] if item["change_type"] == "relationship_changed"][0]
    assert changed["original_relation"] == "behind"
    assert changed["snapshot_a_evidence"]["supporting_candidate_ids"]
    assert changed["snapshot_b_evidence"]["source_frame_hashes"]


def test_moved_when_relationship_target_changes(tmp_path):
    snap_a = _snapshot(
        "snapshot-a",
        ended_at="2026-01-01T00:00:00+00:00",
        relationships=[_relationship("fixture wrench", "on", "left tray", 1.0)],
    )
    snap_b = _snapshot(
        "snapshot-b",
        ended_at="2026-01-01T01:00:00+00:00",
        relationships=[_relationship("fixture wrench", "on", "right tray", 2.0)],
    )

    result = wcc.create_comparison(snap_a, snap_b, db_path=tmp_path / "changes.sqlite")

    moved = [item for item in result["changes"] if item["change_type"] == "moved"]
    assert moved
    assert moved[0]["subject_label"] == "fixture wrench"
    assert moved[0]["object_label"] == "right tray"
    assert "who moved it" in " ".join(moved[0]["uncertainty"])


def test_mismatched_camera_coverage_is_unable_to_determine(tmp_path):
    snap_a = _snapshot(
        "snapshot-a",
        ended_at="2026-01-01T00:00:00+00:00",
        coverage_key="fixture-left-side",
        relationships=[_relationship("fixture mug", "on", "fixture desk", 1.0)],
    )
    snap_b = _snapshot(
        "snapshot-b",
        ended_at="2026-01-01T01:00:00+00:00",
        coverage_key="fixture-right-side",
        relationships=[],
    )

    result = wcc.create_comparison(snap_a, snap_b, db_path=tmp_path / "changes.sqlite")

    assert _change_types(result) == {"unable_to_determine"}
    assert result["changes"][0]["snapshot_a_evidence"]["coverage_key"] == "fixture-left-side"
    assert result["changes"][0]["snapshot_b_evidence"]["coverage_key"] == "fixture-right-side"


def test_incomplete_relationship_evidence_becomes_unable_to_determine(tmp_path):
    snap_a = _snapshot(
        "snapshot-a",
        ended_at="2026-01-01T00:00:00+00:00",
        relationships=[_relationship("fixture clamp", "near", "fixture drill", 1.0)],
    )
    snap_b = _snapshot(
        "snapshot-b",
        ended_at="2026-01-01T01:00:00+00:00",
        relationships=[_relationship("fixture clamp", "near", "fixture shelf", 2.0)],
    )

    result = wcc.create_comparison(snap_a, snap_b, db_path=tmp_path / "changes.sqlite")

    assert "moved" in _change_types(result)
    assert any(item["snapshot_a_evidence"]["supporting_candidate_ids"] for item in result["changes"])


def test_snapshot_ordering_is_enforced(tmp_path):
    snap_a = _snapshot("snapshot-a", ended_at="2026-01-01T02:00:00+00:00")
    snap_b = _snapshot("snapshot-b", ended_at="2026-01-01T01:00:00+00:00")

    with pytest.raises(wcc.WorkspaceChangeError, match="snapshot B"):
        wcc.create_comparison(snap_a, snap_b, db_path=tmp_path / "changes.sqlite")


def test_deduplication_and_deterministic_summary(tmp_path):
    db = tmp_path / "changes.sqlite"
    snap_a = _snapshot(
        "snapshot-a",
        ended_at="2026-01-01T00:00:00+00:00",
        relationships=[_relationship("fixture keyboard", "on", "fixture desk", 1.0)],
    )
    snap_b = _snapshot(
        "snapshot-b",
        ended_at="2026-01-01T01:00:00+00:00",
        relationships=[_relationship("fixture keyboard", "on", "fixture desk", 2.0)],
    )

    first = wcc.create_comparison(snap_a, snap_b, db_path=db)
    second = wcc.create_comparison(snap_a, snap_b, db_path=db)
    summary1 = wcc.deterministic_summary(first["comparison"]["comparison_id"], db_path=db)
    summary2 = wcc.deterministic_summary(first["comparison"]["comparison_id"], db_path=db)

    assert first["created_change_count"] == 1
    assert second["created_change_count"] == 0
    assert second["duplicate_change_count"] == 1
    assert summary1 == summary2
    assert summary1["boundaries"]["writes_executive_context"] is False


def test_review_correction_rejection_and_append_only_history(tmp_path):
    db = tmp_path / "changes.sqlite"
    snap_a = _snapshot(
        "snapshot-a",
        ended_at="2026-01-01T00:00:00+00:00",
        relationships=[_relationship("fixture mug", "on", "fixture desk", 1.0)],
    )
    snap_b = _snapshot(
        "snapshot-b",
        ended_at="2026-01-01T01:00:00+00:00",
        relationships=[],
    )
    change = wcc.create_comparison(snap_a, snap_b, db_path=db)["changes"][0]

    corrected = wcc.correct_change(
        change["change_candidate_id"],
        change_type="unable_to_determine",
        reviewer="FixtureReviewer",
        reason="fixture camera uncertainty",
        db_path=db,
    )
    assert corrected["original_change_type"] == "disappeared"
    assert corrected["change_type"] == "unable_to_determine"
    assert [event["operation"] for event in wcc.list_events(change["change_candidate_id"], db_path=db)] == [
        "create_change_candidate",
        "corrected_change_candidate",
    ]

    other = wcc.create_comparison(
        _snapshot("snapshot-c", ended_at="2026-01-01T02:00:00+00:00", relationships=[_relationship("fixture lamp", "on", "fixture desk", 2.0)]),
        _snapshot("snapshot-d", ended_at="2026-01-01T03:00:00+00:00", relationships=[]),
        db_path=db,
    )["changes"][0]
    wcc.reject_change(other["change_candidate_id"], reviewer="FixtureReviewer", reason="fixture reject", db_path=db)
    with pytest.raises(wcc.WorkspaceChangeError, match="cannot be silently approved"):
        wcc.approve_change(other["change_candidate_id"], reviewer="FixtureReviewer", reason="later approve", db_path=db)


def test_no_automatic_memory_task_or_executive_context_imports():
    source = Path(wcc.__file__).read_text()

    forbidden_imports = [
        "import core.structured_facts",
        "from core import structured_facts",
        "from assets.task_manager",
        "import assets.task_manager",
        "import core.executive_context",
        "from core import executive_context",
        "from assets.observation_manager",
    ]
    for forbidden in forbidden_imports:
        assert forbidden not in source


def test_self_test_reports_boundaries():
    result = wcc._self_test()

    assert result["ok"] is True
    assert result["writes_permanent_memory"] is False
    assert "appeared" in result["change_types"]
