from __future__ import annotations

import json
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


def test_ollama_call_sends_image_data(tmp_path, monkeypatch):
    frame = tmp_path / "frame.jpg"
    _make_image(frame)
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"message": {"content": "{\"objects\": []}"}}).encode()

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(vac.urllib.request, "urlopen", fake_urlopen)

    raw = vac.call_ollama_vision(frame, model_name="fixture-vision")

    assert captured["body"]["model"] == "fixture-vision"
    assert captured["body"]["messages"][0]["images"][0]
    assert raw["request_structure"]["messages"][0]["images"] == ["<base64 image omitted>"]


def test_text_only_ollama_model_is_rejected(tmp_path, monkeypatch):
    frame = {"frame_id": "frame-001", "timestamp_seconds": 2.0}
    image_path = tmp_path / "frame.jpg"
    _make_image(image_path)
    frame_info = {"path": str(image_path), "sha256": "abc", "width": 80, "height": 60, "format": "JPEG"}
    monkeypatch.setattr(vac, "get_ollama_model_info", lambda *args, **kwargs: {"capabilities": ["completion"]})

    with pytest.raises(vac.VisualAnalysisError, match="does not report image"):
        vac.analyze_frame_pixels(frame, frame_info, method=vac.OLLAMA_QWEN25VL_METHOD)


def test_malformed_ollama_json_produces_no_candidates(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(vac, "get_ollama_model_info", lambda *args, **kwargs: {"capabilities": ["vision"]})
    monkeypatch.setattr(vac, "call_ollama_vision", lambda *args, **kwargs: {"content": "not json"})

    result = vac.analyze_video_candidate(
        candidate["candidate_id"],
        db_path=tmp_path / "visual.sqlite",
        video_db_path=tmp_path / "video.sqlite",
        method=vac.OLLAMA_QWEN25VL_METHOD,
        frame_timestamp=2.0,
    )

    assert result["created_count"] == 0
    assert result["analysis_errors"][0]["error_type"] == "malformed_model_output"
    assert vac.list_visual_candidates(video_candidate_id=candidate["candidate_id"], db_path=tmp_path / "visual.sqlite") == []


def test_ollama_top_level_json_list_is_accepted(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(vac, "get_ollama_model_info", lambda *args, **kwargs: {"capabilities": ["vision"]})
    monkeypatch.setattr(
        vac,
        "call_ollama_vision",
        lambda *args, **kwargs: {
            "content": json.dumps([{"label": "fixture mug", "confidence": 0.8, "uncertainty": "fixture visible object"}])
        },
    )

    result = vac.analyze_video_candidate(
        candidate["candidate_id"],
        db_path=tmp_path / "visual.sqlite",
        video_db_path=tmp_path / "video.sqlite",
        method=vac.OLLAMA_QWEN25VL_METHOD,
        frame_timestamp=2.0,
    )

    assert result["created_count"] == 1
    assert result["candidates"][0]["proposed_label"] == "fixture mug"


def test_ollama_confidence_is_bounded_and_candidate_remains_pending(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(vac, "get_ollama_model_info", lambda *args, **kwargs: {"capabilities": ["vision"]})
    monkeypatch.setattr(
        vac,
        "call_ollama_vision",
        lambda *args, **kwargs: {
            "content": json.dumps({
                "objects": [{
                    "label": "fixture keyboard",
                    "confidence": 3.2,
                    "uncertainty": "fixture uncertainty",
                    "alternate_labels": ["fixture input device"],
                }]
            })
        },
    )

    result = vac.analyze_video_candidate(
        candidate["candidate_id"],
        db_path=tmp_path / "visual.sqlite",
        video_db_path=tmp_path / "video.sqlite",
        method=vac.OLLAMA_QWEN25VL_METHOD,
        frame_timestamp=2.0,
    )

    created = result["candidates"][0]
    assert created["confidence"] == 1.0
    assert created["status"] == "pending_review"
    assert created["source_frame_hash"]
    assert created["frame_timestamp"] == 2.0
    assert "bounded" in " ".join(created["uncertainty"])


def test_repeated_ollama_analysis_deduplicates_one_frame(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(vac, "get_ollama_model_info", lambda *args, **kwargs: {"capabilities": ["vision"]})
    monkeypatch.setattr(
        vac,
        "call_ollama_vision",
        lambda *args, **kwargs: {"content": json.dumps({"objects": [{"label": "fixture hand tool", "confidence": 0.7}]})},
    )

    first = vac.analyze_video_candidate(
        candidate["candidate_id"],
        db_path=tmp_path / "visual.sqlite",
        video_db_path=tmp_path / "video.sqlite",
        method=vac.OLLAMA_QWEN25VL_METHOD,
        frame_timestamp=2.0,
    )
    second = vac.analyze_video_candidate(
        candidate["candidate_id"],
        db_path=tmp_path / "visual.sqlite",
        video_db_path=tmp_path / "video.sqlite",
        method=vac.OLLAMA_QWEN25VL_METHOD,
        frame_timestamp=2.0,
    )

    assert first["created_count"] == 1
    assert second["created_count"] == 0
    assert second["duplicate_count"] == 1


def test_ollama_failure_leaves_existing_candidate_state_intact(tmp_path, monkeypatch):
    candidate = _video_candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(vac, "get_ollama_model_info", lambda *args, **kwargs: {"capabilities": ["vision"]})
    monkeypatch.setattr(
        vac,
        "call_ollama_vision",
        lambda *args, **kwargs: {"content": json.dumps({"objects": [{"label": "fixture mug", "confidence": 0.7}]})},
    )
    created = vac.analyze_video_candidate(
        candidate["candidate_id"],
        db_path=tmp_path / "visual.sqlite",
        video_db_path=tmp_path / "video.sqlite",
        method=vac.OLLAMA_QWEN25VL_METHOD,
        frame_timestamp=2.0,
    )["candidates"][0]

    def broken_call(*args, **kwargs):
        raise vac.VisualAnalysisError("fixture network failure")

    monkeypatch.setattr(vac, "call_ollama_vision", broken_call)

    with pytest.raises(vac.VisualAnalysisError, match="fixture network failure"):
        vac.analyze_video_candidate(
            candidate["candidate_id"],
            db_path=tmp_path / "visual.sqlite",
            video_db_path=tmp_path / "video.sqlite",
            method=vac.OLLAMA_QWEN25VL_METHOD,
            frame_timestamp=2.0,
        )
    assert vac.get_visual_candidate(created["visual_candidate_id"], db_path=tmp_path / "visual.sqlite")["status"] == "pending_review"
