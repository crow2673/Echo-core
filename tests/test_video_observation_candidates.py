from __future__ import annotations

from pathlib import Path

import pytest

from assets.asset_database import AssetDatabase
from assets.video_observation_candidates import (
    VideoCandidateError,
    approve_candidate,
    get_candidate,
    ingest_video,
    list_events,
    reject_candidate,
)
from core import companion_session


def _fake_extractors(monkeypatch):
    monkeypatch.setattr(
        "assets.video_observation_candidates.inspect_video_metadata",
        lambda _path: {"format": {"duration": "9.0"}, "streams": [{"codec_type": "video", "codec_name": "h264"}]},
    )

    def fake_frames(_path: Path, *, output_dir: Path, duration_seconds: float, max_frames: int):
        output_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for idx, ts in enumerate([3.0, 6.0][:max_frames], start=1):
            frame = output_dir / f"frame_{idx}.jpg"
            frame.write_bytes(f"fixture-frame-{idx}".encode())
            frames.append({
                "frame_id": f"frame-{idx:03d}",
                "timestamp_seconds": ts,
                "path": str(frame),
                "sha256": f"hash-{idx}",
                "bytes": frame.stat().st_size,
            })
        return frames

    monkeypatch.setattr("assets.video_observation_candidates.extract_representative_frames", fake_frames)


def _video(tmp_path: Path) -> Path:
    path = tmp_path / "fixture_video.mp4"
    path.write_bytes(b"not a real video; extractor is monkeypatched")
    return path


def test_video_intake_creates_candidate_not_observation(tmp_path, monkeypatch):
    _fake_extractors(monkeypatch)
    video = _video(tmp_path)
    candidate_db = tmp_path / "candidates.sqlite"
    asset_db = AssetDatabase(tmp_path / "assets.sqlite")

    result = ingest_video(video, asset_id="FIXTURE-ASSET-01", db_path=candidate_db, evidence_dir=tmp_path / "evidence")

    assert result["duplicate"] is False
    candidate = result["candidate"]
    assert candidate["status"] == "pending_review"
    assert candidate["inferred_candidate_facts"] == {}
    assert "No visual facts were inferred automatically" in candidate["raw_description"]
    assert asset_db.recent_observations(asset_id="FIXTURE-ASSET-01", limit=5) == []


def test_repeated_intake_deduplicates_same_video(tmp_path, monkeypatch):
    _fake_extractors(monkeypatch)
    video = _video(tmp_path)
    db = tmp_path / "candidates.sqlite"

    first = ingest_video(video, asset_id="FIXTURE-ASSET-01", db_path=db, evidence_dir=tmp_path / "evidence")
    second = ingest_video(video, asset_id="FIXTURE-ASSET-01", db_path=db, evidence_dir=tmp_path / "evidence")

    assert second["duplicate"] is True
    assert second["candidate"]["candidate_id"] == first["candidate"]["candidate_id"]


def test_evidence_frames_retain_source_timestamps_and_survive_fresh_process(tmp_path, monkeypatch):
    _fake_extractors(monkeypatch)
    result = ingest_video(_video(tmp_path), db_path=tmp_path / "candidates.sqlite", evidence_dir=tmp_path / "evidence")
    candidate_id = result["candidate"]["candidate_id"]

    fresh = get_candidate(candidate_id, db_path=tmp_path / "candidates.sqlite")

    assert [frame["timestamp_seconds"] for frame in fresh["evidence_frame_references"]] == [3.0, 6.0]


def test_pending_candidate_requires_review_before_asset_history(tmp_path, monkeypatch):
    _fake_extractors(monkeypatch)
    result = ingest_video(_video(tmp_path), db_path=tmp_path / "candidates.sqlite", evidence_dir=tmp_path / "evidence")

    with pytest.raises(VideoCandidateError, match="confirmed_facts"):
        approve_candidate(
            result["candidate"]["candidate_id"],
            reviewer="FixtureReviewer",
            reason="reviewed fixture",
            confirmed_facts={},
            asset_id="FIXTURE-ASSET-01",
            db_path=tmp_path / "candidates.sqlite",
            asset_db_path=tmp_path / "assets.sqlite",
            observations_dir=tmp_path / "observations",
        )


def test_approval_routes_through_observation_manager(tmp_path, monkeypatch):
    _fake_extractors(monkeypatch)
    result = ingest_video(_video(tmp_path), db_path=tmp_path / "candidates.sqlite", evidence_dir=tmp_path / "evidence")
    candidate_id = result["candidate"]["candidate_id"]

    approved = approve_candidate(
        candidate_id,
        reviewer="FixtureReviewer",
        reason="confirmed fixture frame shows inspected connector",
        confirmed_facts={"fixture_connector_visible": True},
        asset_id="FIXTURE-ASSET-01",
        db_path=tmp_path / "candidates.sqlite",
        asset_db_path=tmp_path / "assets.sqlite",
        observations_dir=tmp_path / "observations",
    )

    observations = AssetDatabase(tmp_path / "assets.sqlite").recent_observations(asset_id="FIXTURE-ASSET-01", limit=5)
    assert approved["candidate"]["status"] == "approved"
    assert approved["observation_result"]["structured"] is True
    assert len(observations) == 1
    assert observations[0]["payload"]["extracted_facts"] == {"fixture_connector_visible": True}


def test_rejection_prevents_later_approval_and_history_is_append_only(tmp_path, monkeypatch):
    _fake_extractors(monkeypatch)
    result = ingest_video(_video(tmp_path), db_path=tmp_path / "candidates.sqlite", evidence_dir=tmp_path / "evidence")
    candidate_id = result["candidate"]["candidate_id"]

    reject_candidate(candidate_id, reviewer="FixtureReviewer", reason="fixture not useful", db_path=tmp_path / "candidates.sqlite")

    with pytest.raises(VideoCandidateError, match="rejected candidates cannot be approved"):
        approve_candidate(
            candidate_id,
            reviewer="FixtureReviewer",
            reason="changed mind",
            confirmed_facts={"x": True},
            asset_id="FIXTURE-ASSET-01",
            db_path=tmp_path / "candidates.sqlite",
            asset_db_path=tmp_path / "assets.sqlite",
            observations_dir=tmp_path / "observations",
        )
    events = list_events(candidate_id, db_path=tmp_path / "candidates.sqlite")
    assert [event["operation"] for event in events] == ["create_candidate", "reject_candidate"]


def test_source_privacy_retained_and_no_auto_task_or_fact(tmp_path, monkeypatch):
    _fake_extractors(monkeypatch)
    candidate = ingest_video(
        _video(tmp_path),
        privacy_scope="owner_private",
        db_path=tmp_path / "candidates.sqlite",
        evidence_dir=tmp_path / "evidence",
    )["candidate"]

    assert candidate["privacy_scope"] == "owner_private"
    assert "task" not in candidate
    assert "structured_fact" not in candidate


def test_companion_session_references_candidate_without_duplicating_contents(tmp_path, monkeypatch):
    _fake_extractors(monkeypatch)
    candidate = ingest_video(_video(tmp_path), db_path=tmp_path / "candidates.sqlite", evidence_dir=tmp_path / "evidence")["candidate"]
    session = companion_session.start_session(
        title="Fixture video review session",
        purpose="Track candidate review without copying private contents",
        current_step="Review candidate reference",
        next_action="Open candidate by ID",
        db_path=tmp_path / "sessions.sqlite",
    )

    updated = companion_session.record_update(
        session["session_id"],
        current_step=f"Review candidate {candidate['candidate_id']}",
        next_action="Inspect frame references",
        db_path=tmp_path / "sessions.sqlite",
    )

    assert candidate["raw_description"] not in str(updated)
    assert candidate["candidate_id"] in updated["current_step"]
