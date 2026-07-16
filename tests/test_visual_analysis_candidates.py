from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from assets import visual_analysis_candidates as vac
from assets.asset_database import AssetDatabase
from assets.video_observation_candidates import ingest_video
from core import companion_session


def _make_image(path: Path, color: str = "white") -> None:
    Image.new("RGB", (80, 60), color=color).save(path, format="JPEG")


def _video_candidate(tmp_path: Path, monkeypatch, *, missing_frame: bool = False) -> dict:
    def fake_metadata(_path):
        return {"format": {"duration": "6.0"}, "streams": [{"codec_type": "video", "codec_name": "fixture"}]}

    def fake_frames(_path: Path, *, output_dir: Path, duration_seconds: float, max_frames: int):
        output_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for idx, ts in enumerate([2.0, 4.0], start=1):
            frame = output_dir / f"fixture_frame_{idx}.jpg"
            if not missing_frame:
                _make_image(frame, "white" if idx == 1 else "gray")
            frames.append({
                "frame_id": f"frame-{idx:03d}",
                "timestamp_seconds": ts,
                "path": str(frame),
                "sha256": vac.hashlib.sha256(frame.read_bytes()).hexdigest() if frame.exists() else "missing",
                "bytes": frame.stat().st_size if frame.exists() else 0,
            })
        return frames

    monkeypatch.setattr("assets.video_observation_candidates.inspect_video_metadata", fake_metadata)
    monkeypatch.setattr("assets.video_observation_candidates.extract_representative_frames", fake_frames)
    video = tmp_path / "fixture_video.mp4"
    video.write_bytes(b"fixture video source")
    return ingest_video(video, db_path=tmp_path / "video.sqlite", evidence_dir=tmp_path / "evidence")["candidate"]


def _fixture_analyzer(frame, frame_info, *, method):
    return [
        {
            "proposed_label": "fixture mug",
            "broad_category": "container",
            "confidence": 0.62,
            "alternate_labels": ["fixture cup"],
            "uncertainty": ["small object; exact type uncertain"],
            "source_model": "fixture_pixel_analyzer",
            "model_version": "fixture-v1",
        },
        {
            "proposed_label": "fixture mug",
            "confidence": 0.5,
        },
    ]


def test_analysis_cannot_run_without_readable_frame_evidence(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch, missing_frame=True)

    with pytest.raises(vac.VisualAnalysisError, match="frame evidence missing"):
        vac.analyze_video_candidate(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite", video_db_path=tmp_path / "video.sqlite")


def test_object_candidates_reference_frame_hashes_and_timestamps(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(vac, "analyze_frame_pixels", _fixture_analyzer)

    result = vac.analyze_video_candidate(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite", video_db_path=tmp_path / "video.sqlite")

    assert result["created_count"] == 2
    first = result["candidates"][0]
    assert first["source_frame_hash"]
    assert first["frame_timestamp"] in {2.0, 4.0}
    assert first["status"] == "pending_review"
    assert first["alternate_labels"] == ["fixture cup"]


def test_no_permanent_observation_structured_fact_or_task_before_review(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(vac, "analyze_frame_pixels", _fixture_analyzer)
    vac.analyze_video_candidate(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite", video_db_path=tmp_path / "video.sqlite")

    db = AssetDatabase(tmp_path / "assets.sqlite")
    summary = db.asset_summary()
    assert summary["observations"] == 0
    assert summary["open_tasks"] == 0


def test_repeated_analysis_deduplicates_identical_candidates(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(vac, "analyze_frame_pixels", _fixture_analyzer)

    first = vac.analyze_video_candidate(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite", video_db_path=tmp_path / "video.sqlite")
    second = vac.analyze_video_candidate(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite", video_db_path=tmp_path / "video.sqlite")

    assert first["created_count"] == 2
    assert second["created_count"] == 0
    assert second["duplicate_count"] == 2


def test_correction_preserves_original_model_label_and_history(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(vac, "analyze_frame_pixels", _fixture_analyzer)
    created = vac.analyze_video_candidate(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite", video_db_path=tmp_path / "video.sqlite")["candidates"][0]

    corrected = vac.correct_candidate(
        created["visual_candidate_id"],
        label="fixture cup",
        reviewer="FixtureReviewer",
        reason="fixture correction",
        db_path=tmp_path / "visual.sqlite",
    )

    assert corrected["proposed_label"] == "fixture mug"
    assert corrected["corrected_label"] == "fixture cup"
    assert corrected["status"] == "corrected"
    assert [event["operation"] for event in vac.list_events(created["visual_candidate_id"], db_path=tmp_path / "visual.sqlite")] == [
        "create_visual_candidate",
        "corrected_visual_candidate",
    ]


def test_rejection_prevents_silent_approval(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(vac, "analyze_frame_pixels", _fixture_analyzer)
    created = vac.analyze_video_candidate(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite", video_db_path=tmp_path / "video.sqlite")["candidates"][0]

    vac.reject_candidate(created["visual_candidate_id"], reviewer="FixtureReviewer", reason="fixture reject", db_path=tmp_path / "visual.sqlite")

    with pytest.raises(vac.VisualAnalysisError, match="rejected candidates cannot be silently approved"):
        vac.approve_candidate(created["visual_candidate_id"], reviewer="FixtureReviewer", reason="fixture approve", db_path=tmp_path / "visual.sqlite")


def test_candidate_state_survives_fresh_process_and_consolidates(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(vac, "analyze_frame_pixels", _fixture_analyzer)
    result = vac.analyze_video_candidate(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite", video_db_path=tmp_path / "video.sqlite")
    first_id = result["candidates"][0]["visual_candidate_id"]

    fresh = vac.get_visual_candidate(first_id, db_path=tmp_path / "visual.sqlite")
    consolidated = vac.consolidate_candidates(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite")

    assert fresh["visual_candidate_id"] == first_id
    assert consolidated[0]["label"] == "fixture mug"
    assert consolidated[0]["supporting_timestamps"] == [2.0, 4.0]


def test_private_paths_are_not_in_review_summary(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(vac, "analyze_frame_pixels", _fixture_analyzer)
    vac.analyze_video_candidate(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite", video_db_path=tmp_path / "video.sqlite")

    summary = vac.review_summary(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite")

    assert "path" not in str(summary).lower()
    assert "fixture mug" in str(summary)


def test_face_recognition_or_person_identification_is_blocked(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)

    def bad_analyzer(frame, frame_info, *, method):
        return [{"proposed_label": "person", "person_identification": True}]

    monkeypatch.setattr(vac, "analyze_frame_pixels", bad_analyzer)

    with pytest.raises(vac.VisualAnalysisError, match="person identification"):
        vac.analyze_video_candidate(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite", video_db_path=tmp_path / "video.sqlite")


def test_no_model_method_checks_frames_but_does_not_invent_labels(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)

    result = vac.analyze_video_candidate(candidate["candidate_id"], db_path=tmp_path / "visual.sqlite", video_db_path=tmp_path / "video.sqlite")

    assert result["created_count"] == 0
    assert result["frames_checked"]
    assert result["missing_capability"]["missing_capability"] == "local_vision_model_or_object_detector"


def test_companion_session_stores_state_without_frame_contents(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    session = companion_session.start_session(
        title="Fixture visual analysis session",
        purpose="Track visual candidate review without copying frame contents",
        current_step=f"Analyze video candidate {candidate['candidate_id']}",
        next_action="Open visual candidate list",
        db_path=tmp_path / "sessions.sqlite",
    )

    updated = companion_session.record_update(
        session["session_id"],
        current_step=f"Visual analysis candidate reference for {candidate['candidate_id']}",
        db_path=tmp_path / "sessions.sqlite",
    )

    assert ".jpg" not in str(updated)
    assert candidate["candidate_id"] in updated["current_step"]
