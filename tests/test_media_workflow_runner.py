from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import media_workflow_runner as runner


def make_manifest(tmp_path: Path, fail_stage: str | None = None) -> Path:
    work = tmp_path / "work"
    manifest = {
        "workflow_id": "test_media_workflow",
        "work_dir": str(work),
        "external_services_allowed": False,
        "external_required_stages": [
            {"stage_id": "external_avatar", "status": "blocked", "reason": "external service"}
        ],
        "stages": [
            {"stage_id": "intake", "handler": "fake", "inputs": [], "outputs": [str(work / "intake.txt")], "dependencies": [], "retryable": True},
            {"stage_id": "segment_script", "handler": "fake_fail" if fail_stage == "segment_script" else "fake", "inputs": [str(work / "intake.txt")], "outputs": [str(work / "segments.json")], "dependencies": ["intake"], "retryable": True},
            {"stage_id": "generate_placeholder_audio", "handler": "fake", "inputs": [str(work / "segments.json")], "outputs": [str(work / "audio.wav")], "dependencies": ["segment_script"], "retryable": True},
            {"stage_id": "write_final_manifest", "handler": "fake_manifest", "inputs": [str(work / "audio.wav")], "outputs": [str(work / "final_manifest.json")], "dependencies": ["generate_placeholder_audio"], "retryable": True}
        ]
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def make_review_manifest(tmp_path: Path) -> Path:
    work = tmp_path / "review_work"
    manifest = {
        "workflow_id": "review_media_workflow",
        "work_dir": str(work),
        "external_services_allowed": False,
        "external_required_stages": [
            {"stage_id": "commercial_avatar_generation", "status": "blocked", "reason": "external service"}
        ],
        "stages": [
            {"stage_id": "intake", "handler": "fake", "inputs": [], "outputs": [str(work / "intake.txt")], "dependencies": [], "retryable": True},
            {"stage_id": "quality_check", "handler": "fake_quality", "inputs": [str(work / "intake.txt")], "outputs": [str(work / "quality.json")], "dependencies": ["intake"], "retryable": True},
            {"stage_id": "export", "handler": "fake_copy", "inputs": [str(work / "intake.txt"), str(work / "quality.json")], "outputs": [str(work / "final.mp4")], "dependencies": ["quality_check"], "retryable": True},
            {"stage_id": "write_final_manifest", "handler": "fake_manifest", "inputs": [str(work / "final.mp4")], "outputs": [str(work / "final_manifest.json")], "dependencies": ["export"], "retryable": True}
        ]
    }
    path = tmp_path / "review_manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def make_stage_review_manifest(tmp_path: Path) -> Path:
    work = tmp_path / "stage_review_work"
    manifest = {
        "workflow_id": "stage_review_media_workflow",
        "work_dir": str(work),
        "external_services_allowed": False,
        "external_required_stages": [
            {"stage_id": "commercial_avatar_generation", "status": "blocked", "reason": "external service"}
        ],
        "stages": [
            {"stage_id": "intake", "handler": "fake", "inputs": [], "outputs": [str(work / "intake.txt")], "dependencies": [], "retryable": True, "human_review_required": False},
            {"stage_id": "segment_script", "handler": "fake", "inputs": [str(work / "intake.txt")], "outputs": [str(work / "segments.json")], "dependencies": ["intake"], "retryable": True, "human_review_required": True},
            {"stage_id": "generate_placeholder_audio", "handler": "fake", "inputs": [str(work / "segments.json")], "outputs": [str(work / "audio.wav")], "dependencies": ["segment_script"], "retryable": True, "human_review_required": True},
            {"stage_id": "quality_check", "handler": "fake_quality", "inputs": [str(work / "audio.wav")], "outputs": [str(work / "quality.json")], "dependencies": ["generate_placeholder_audio"], "retryable": True, "human_review_required": True},
            {"stage_id": "export", "handler": "fake_copy", "inputs": [str(work / "audio.wav"), str(work / "quality.json")], "outputs": [str(work / "final.mp4")], "dependencies": ["quality_check"], "retryable": True, "human_review_required": False},
            {"stage_id": "write_final_manifest", "handler": "fake_manifest", "inputs": [str(work / "final.mp4")], "outputs": [str(work / "final_manifest.json")], "dependencies": ["export"], "retryable": True, "human_review_required": False}
        ]
    }
    path = tmp_path / "stage_review_manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def scene_card_style_data() -> dict:
    return {
        "schema_version": 1,
        "profiles": {
            "clean_default": {
                "canvas_width": 360,
                "canvas_height": 640,
                "frame_rate": 15,
                "background_mode": "gradient",
                "background_color": "#122542",
                "background_gradient": ["#122542", "#267491"],
                "foreground_color": "#E8F4F8",
                "accent_color": "#E8F4F8",
                "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "title_font_size": 24,
                "body_font_size": 18,
                "minimum_font_size": 12,
                "line_spacing": 6,
                "horizontal_margin": 28,
                "vertical_margin": 36,
                "text_alignment": "left",
                "vertical_alignment": "center",
                "maximum_lines": 7,
                "maximum_characters_per_card": 90,
                "card_duration_seconds": 2.0,
                "transition_type": "cut",
                "transition_duration_seconds": 0.0,
                "show_scene_number": True,
                "show_progress_indicator": True,
                "safe_area": {"left": 24, "top": 64, "right": 24, "bottom": 72},
                "deterministic_seed": 42,
            },
            "technical_brief": {
                "canvas_width": 360,
                "canvas_height": 640,
                "frame_rate": 15,
                "background_mode": "solid",
                "background_color": "#111820",
                "background_gradient": ["#111820", "#1F3642"],
                "foreground_color": "#F1F5F9",
                "accent_color": "#38BDF8",
                "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "title_font_size": 20,
                "body_font_size": 16,
                "minimum_font_size": 10,
                "line_spacing": 5,
                "horizontal_margin": 24,
                "vertical_margin": 30,
                "text_alignment": "left",
                "vertical_alignment": "top",
                "maximum_lines": 9,
                "maximum_characters_per_card": 130,
                "card_duration_seconds": 2.0,
                "transition_type": "cut",
                "transition_duration_seconds": 0.0,
                "show_scene_number": True,
                "show_progress_indicator": True,
                "safe_area": {"left": 22, "top": 58, "right": 22, "bottom": 66},
                "deterministic_seed": 43,
            },
            "high_contrast": {
                "canvas_width": 360,
                "canvas_height": 640,
                "frame_rate": 15,
                "background_mode": "solid",
                "background_color": "#050505",
                "background_gradient": ["#050505", "#1A1A1A"],
                "foreground_color": "#FFFFFF",
                "accent_color": "#FFD400",
                "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "title_font_size": 26,
                "body_font_size": 20,
                "minimum_font_size": 13,
                "line_spacing": 7,
                "horizontal_margin": 30,
                "vertical_margin": 38,
                "text_alignment": "center",
                "vertical_alignment": "center",
                "maximum_lines": 6,
                "maximum_characters_per_card": 75,
                "card_duration_seconds": 2.0,
                "transition_type": "cut",
                "transition_duration_seconds": 0.0,
                "show_scene_number": True,
                "show_progress_indicator": True,
                "safe_area": {"left": 24, "top": 66, "right": 24, "bottom": 76},
                "deterministic_seed": 44,
            },
        },
    }


def make_scene_cards_manifest(
    tmp_path: Path,
    profile: str = "clean_default",
    style_data: dict | None = None,
    script_text: str = "First scene explains the shift. Second scene shows the proof.",
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    work = tmp_path / "scene_work"
    script = tmp_path / "script.txt"
    script.write_text(script_text)
    style = tmp_path / "scene_card_style.json"
    style.write_text(json.dumps(style_data or scene_card_style_data()))
    manifest = {
        "workflow_id": "scene_card_test",
        "work_dir": str(work),
        "fixture_dir": str(tmp_path),
        "external_services_allowed": False,
        "external_required_stages": [],
        "stages": [
            {"stage_id": "intake", "handler": "intake", "inputs": [str(script)], "outputs": [str(work / "intake.txt")], "dependencies": [], "retryable": True, "human_review_required": False},
            {"stage_id": "segment_script", "handler": "segment_script", "inputs": [str(work / "intake.txt")], "outputs": [str(work / "segments.json")], "dependencies": ["intake"], "retryable": True, "human_review_required": True},
            {"stage_id": "generate_placeholder_audio", "handler": "generate_placeholder_audio", "inputs": [str(work / "segments.json")], "outputs": [str(work / "audio.wav")], "dependencies": ["segment_script"], "retryable": True, "human_review_required": True},
            {"stage_id": "generate_placeholder_visual", "handler": "generate_scene_cards_visual", "fallback_handler": "generate_placeholder_visual", "style_config_path": str(style), "style_profile": profile, "inputs": [str(work / "segments.json"), str(style)], "outputs": [str(work / "scene_cards.mp4")], "dependencies": ["segment_script"], "retryable": True, "human_review_required": True},
            {"stage_id": "generate_captions", "handler": "generate_captions", "inputs": [str(work / "segments.json")], "outputs": [str(work / "captions.srt")], "dependencies": ["segment_script"], "retryable": True, "human_review_required": True},
            {"stage_id": "assemble_video", "handler": "assemble_video", "inputs": [str(work / "audio.wav"), str(work / "scene_cards.mp4"), str(work / "captions.srt")], "outputs": [str(work / "raw.mp4")], "dependencies": ["generate_placeholder_audio", "generate_placeholder_visual", "generate_captions"], "retryable": True, "human_review_required": True},
            {"stage_id": "quality_check", "handler": "quality_check", "inputs": [str(work / "raw.mp4"), str(work / "captions.srt")], "outputs": [str(work / "quality.json")], "dependencies": ["assemble_video"], "retryable": True, "human_review_required": True},
            {"stage_id": "export", "handler": "export", "inputs": [str(work / "raw.mp4"), str(work / "quality.json")], "outputs": [str(work / "final.mp4")], "dependencies": ["quality_check"], "retryable": True, "human_review_required": True},
            {"stage_id": "write_final_manifest", "handler": "write_final_manifest", "inputs": [str(work / "final.mp4")], "outputs": [str(work / "final_manifest.json")], "dependencies": ["export"], "retryable": True, "human_review_required": False},
        ],
    }
    path = tmp_path / "scene_manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def approve_required_stages(workflow):
    for stage in workflow["stages"]:
        if stage.get("human_review_required"):
            runner.record_stage_review_decision(
                workflow,
                stage["stage_id"],
                "approved",
                reviewer="Andrew",
                notes=f"{stage['stage_id']} ok",
            )


def install_fake_handlers(monkeypatch):
    def fake(workflow, stage):
        out = runner.resolve(stage["outputs"][0])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"{stage['stage_id']}\n")
        runner.complete_stage(stage)

    def fake_fail(workflow, stage):
        raise RuntimeError("intentional failure")

    def fake_manifest(workflow, stage):
        out = runner.resolve(stage["outputs"][0])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"workflow_id": workflow["workflow_id"], "stages": workflow["stages"]}))
        runner.complete_stage(stage)

    def fake_quality(workflow, stage):
        out = runner.resolve(stage["outputs"][0])
        out.parent.mkdir(parents=True, exist_ok=True)
        runner.write_json(out, {
            "ok": True,
            "duration_seconds": 3.0,
            "video_stream_present": True,
            "audio_stream_present": True,
            "captions_present": True,
        })
        runner.complete_stage(stage)

    def fake_copy(workflow, stage):
        src = runner.resolve(stage["inputs"][0])
        out = runner.resolve(stage["outputs"][0])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(src.read_text() + "video\n")
        runner.complete_stage(stage)

    handlers = dict(runner.HANDLERS)
    handlers.update({
        "fake": fake,
        "fake_fail": fake_fail,
        "fake_manifest": fake_manifest,
        "fake_quality": fake_quality,
        "fake_copy": fake_copy,
    })
    monkeypatch.setattr(runner, "HANDLERS", handlers)


def test_correct_stage_order():
    result = runner.self_test()
    assert result["ok"] is True
    assert result["plan"]["execution_order"] == [
        "intake",
        "segment_script",
        "generate_placeholder_audio",
        "generate_placeholder_visual",
        "generate_captions",
        "assemble_video",
        "quality_check",
        "export",
        "write_final_manifest",
    ]


def test_dependency_failure_blocks_downstream(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_manifest(tmp_path, fail_stage="segment_script")

    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    statuses = {stage["stage_id"]: stage["status"] for stage in result["workflow"]["stages"]}

    assert statuses["segment_script"] == "failed"
    assert statuses["generate_placeholder_audio"] == "blocked"
    assert statuses["write_final_manifest"] == "blocked"


def test_resume_skips_valid_completed_stages(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_manifest(tmp_path)

    first = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    second = runner.run_workflow(manifest, resume=True)

    assert first["status"]["completed"] == 4
    assert all(item["status"] == "skipped" for item in second["executed"])
    assert second["status"]["completed"] == 4


def test_missing_output_invalidates_completed_stage(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_manifest(tmp_path)
    first = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    audio = Path(first["workflow"]["stages"][2]["outputs"][0])
    audio.unlink()

    status = runner.run_workflow(manifest, status_only=True)

    invalidated = status["invalidated"]
    assert "generate_placeholder_audio" in invalidated
    statuses = {stage["stage_id"]: stage["status"] for stage in status["workflow"]["stages"]}
    assert statuses["generate_placeholder_audio"] == "pending"
    assert statuses["write_final_manifest"] == "pending"


def test_retry_runs_requested_failed_stage_and_dependents(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_manifest(tmp_path, fail_stage="segment_script")
    runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    fixed = json.loads(manifest.read_text())
    for stage in fixed["stages"]:
        if stage["stage_id"] == "segment_script":
            stage["handler"] = "fake"
    manifest.write_text(json.dumps(fixed))
    runtime = runner.runtime_manifest_path(runner.load_workflow(manifest, prefer_runtime=False))
    data = json.loads(runtime.read_text())
    for stage in data["stages"]:
        if stage["stage_id"] == "segment_script":
            stage["handler"] = "fake"
    runtime.write_text(json.dumps(data))

    result = runner.run_workflow(manifest, retry_stage="segment_script")

    statuses = {stage["stage_id"]: stage["status"] for stage in result["workflow"]["stages"]}
    assert statuses == {
        "intake": "completed",
        "segment_script": "completed",
        "generate_placeholder_audio": "completed",
        "write_final_manifest": "completed",
    }


def test_dry_run_creates_no_media(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_manifest(tmp_path)

    result = runner.run_workflow(manifest, dry_run=True, prefer_runtime=False)

    assert result["dry_run"] is True
    assert not (tmp_path / "work").exists()


def test_duplicate_execution_does_not_duplicate_outputs(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_manifest(tmp_path)
    first = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    output_count = len(list((tmp_path / "work").glob("*")))
    second = runner.run_workflow(manifest, resume=True)

    assert len(list((tmp_path / "work").glob("*"))) == output_count
    assert all(item["status"] == "skipped" for item in second["executed"])
    assert first["status"]["completed"] == 4


def test_final_manifest_matches_actual_artifacts(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    final = Path(result["workflow"]["stages"][-1]["outputs"][0])

    assert final.exists()
    data = json.loads(final.read_text())
    assert data["workflow_id"] == "test_media_workflow"
    assert all(Path(stage["outputs"][0]).exists() for stage in result["workflow"]["stages"])


def test_external_required_stages_marked_blocked_without_failing_offline_path(tmp_path):
    manifest = make_manifest(tmp_path)
    plan = runner.run_workflow(manifest, dry_run=True, prefer_runtime=False)

    assert plan["external_required_stages"][0]["status"] == "blocked"


def test_successful_run_starts_as_pending_review(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    review = runner.load_review(result["workflow"])

    assert review["state"] == "pending_review"


def test_approval_records_reviewer_and_fingerprints(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    review = runner.record_review_decision(
        result["workflow"], "approved", reviewer="Andrew", notes="fixture accepted", confirm_approval=True
    )

    assert review["state"] == "approved"
    assert review["reviewer"] == "Andrew"
    assert review["reviewed_artifacts"]["final_output"]["valid"] is True
    assert review["reviewed_artifacts"]["quality_report"]["valid"] is True


def test_rejection_blocks_progression(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    runner.record_review_decision(result["workflow"], "rejected", reviewer="Andrew", reason="not acceptable")

    allowed, reasons = runner.can_proceed_to_external_adapter(result["workflow"])

    assert allowed is False
    assert any("not approved" in reason for reason in reasons)


def test_requested_changes_identify_affected_stages(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    review = runner.record_review_decision(
        result["workflow"],
        "changes_requested",
        reviewer="Andrew",
        notes="replace placeholder audio",
        affected_stages=["intake"],
    )

    assert review["state"] == "changes_requested"
    assert review["affected_stages"] == ["intake"]


def test_changed_output_invalidates_prior_approval(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)
    final_output = Path(runner.stage_by_handler(result["workflow"], "export")["outputs"][0])
    final_output.write_text("changed\n")

    allowed, reasons = runner.can_proceed_to_external_adapter(result["workflow"])
    review = runner.load_review(result["workflow"])

    assert allowed is False
    assert review["state"] == "invalidated"
    assert "final_output" in review["mismatches"]
    assert reasons


def test_rerunning_stage_invalidates_prior_approval(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)

    rerun = runner.run_workflow(manifest, retry_stage="intake")
    allowed, reasons = runner.can_proceed_to_external_adapter(rerun["workflow"])
    review = runner.load_review(rerun["workflow"])

    assert allowed is False
    assert review["state"] == "invalidated"
    assert any(item.startswith("stage_rerun:intake") for item in review["mismatches"])
    assert reasons


def test_unchanged_resume_preserves_valid_approval(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)

    resumed = runner.run_workflow(manifest, resume=True)
    allowed, reasons = runner.can_proceed_to_external_adapter(resumed["workflow"])
    review = runner.load_review(resumed["workflow"])

    assert allowed is True
    assert reasons == []
    assert review["state"] == "approved"


def test_external_progression_denied_without_approval(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    allowed, reasons = runner.can_proceed_to_external_adapter(result["workflow"])

    assert allowed is False
    assert any("not approved" in reason for reason in reasons)


def test_offline_prototype_can_be_approved_while_commercial_stages_disclosed(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)

    allowed, reasons = runner.can_proceed_to_external_adapter(result["workflow"])
    summary = runner.review_summary(result["workflow"])

    assert allowed is True
    assert reasons == []
    assert summary["external_stages_still_blocked"][0]["stage_id"] == "commercial_avatar_generation"


def test_required_stage_begins_pending_review(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    summary = runner.review_summary(result["workflow"])
    required = {item["stage_id"]: item for item in summary["required_stage_reviews"]}

    assert required["segment_script"]["state"] == "pending_review"
    assert required["segment_script"]["blocks_final_approval"] is True


def test_final_approval_denied_before_required_stage_approval(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    with pytest.raises(RuntimeError, match="required stage reviews"):
        runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)


def test_approving_required_stages_permits_final_approval(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    approve_required_stages(result["workflow"])
    review = runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)
    allowed, reasons = runner.can_proceed_to_external_adapter(result["workflow"])

    assert review["state"] == "approved"
    assert allowed is True
    assert reasons == []


def test_rejecting_one_required_stage_blocks_progression(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    approve_required_stages(result["workflow"])
    runner.record_stage_review_decision(
        result["workflow"], "segment_script", "rejected", reviewer="Andrew", reason="bad segment"
    )

    with pytest.raises(RuntimeError, match="segment_script=rejected"):
        runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)


def test_requesting_changes_blocks_progression(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    approve_required_stages(result["workflow"])
    runner.record_stage_review_decision(
        result["workflow"], "quality_check", "changes_requested", reviewer="Andrew", notes="needs clearer audio"
    )

    with pytest.raises(RuntimeError, match="quality_check=changes_requested"):
        runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)


def test_rerunning_one_stage_invalidates_only_its_review_plus_final_approval(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    approve_required_stages(result["workflow"])
    runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)

    rerun = runner.run_workflow(manifest, retry_stage="generate_placeholder_audio")
    allowed, reasons = runner.can_proceed_to_external_adapter(rerun["workflow"])
    review = runner.load_review(rerun["workflow"])

    assert allowed is False
    assert review["state"] == "invalidated"
    assert review["stage_reviews"]["generate_placeholder_audio"]["decision"] == "invalidated"
    assert review["stage_reviews"]["segment_script"]["decision"] == "approved"
    assert any("generate_placeholder_audio" in reason for reason in reasons)


def test_unchanged_resume_preserves_stage_approvals(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    approve_required_stages(result["workflow"])
    runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)

    resumed = runner.run_workflow(manifest, resume=True)
    allowed, reasons = runner.can_proceed_to_external_adapter(resumed["workflow"])
    review = runner.load_review(resumed["workflow"])

    assert allowed is True
    assert reasons == []
    assert all(
        review["stage_reviews"][stage["stage_id"]]["decision"] == "approved"
        for stage in resumed["workflow"]["stages"]
        if stage.get("human_review_required")
    )


def test_optional_stage_review_does_not_become_mandatory(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    approve_required_stages(result["workflow"])

    review = runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)

    assert review["state"] == "approved"


def test_optional_rejected_stage_blocks_only_if_reviewed_and_final_approved_changes(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    approve_required_stages(result["workflow"])
    runner.record_stage_review_decision(
        result["workflow"], "intake", "rejected", reviewer="Andrew", reason="optional note"
    )

    review = runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)

    assert review["state"] == "approved"


def test_blocked_commercial_avatar_disclosed_but_does_not_block_offline_stage_approval(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    approve_required_stages(result["workflow"])
    runner.record_review_decision(result["workflow"], "approved", reviewer="Andrew", confirm_approval=True)

    allowed, reasons = runner.can_proceed_to_external_adapter(result["workflow"])
    summary = runner.review_summary(result["workflow"])

    assert allowed is True
    assert reasons == []
    assert summary["external_stages_still_blocked"][0]["stage_id"] == "commercial_avatar_generation"


def test_stage_inspection_lists_correct_outputs(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    inspection = runner.inspect_stage(result["workflow"], "segment_script", show_fingerprints=True)

    assert inspection["stage_id"] == "segment_script"
    assert inspection["outputs"][0]["path"].endswith("segments.json")
    assert inspection["fingerprints"]["outputs"]["valid"] is True


def test_json_and_text_previews_are_bounded_and_redacted(tmp_path):
    work = tmp_path / "inspect_work"
    work.mkdir()
    secret_json = work / "secret.json"
    secret_json.write_text(json.dumps({"api_key": "123", "normal": "visible"}))
    long_text = work / "long.txt"
    long_text.write_text("\n".join(f"line {idx}" for idx in range(100)))
    workflow = {"workflow_id": "inspect", "work_dir": str(work), "fixture_dir": str(work), "stages": []}

    json_info = runner.inspect_artifact(workflow, str(secret_json))
    text_info = runner.inspect_artifact(workflow, str(long_text))

    assert "[REDACTED]" in json_info["artifact"]["preview"]["preview"]
    assert "visible" in json_info["artifact"]["preview"]["preview"]
    assert text_info["artifact"]["preview"]["truncated"] is True
    assert "line 0" in text_info["artifact"]["preview"]["preview"]


def test_audio_metadata_is_read(tmp_path):
    work = tmp_path / "inspect_work"
    audio = work / "audio.wav"
    runner.write_silent_wav(audio, seconds=1.0)
    workflow = {"workflow_id": "inspect", "work_dir": str(work), "fixture_dir": str(work), "stages": []}

    info = runner.inspect_artifact(workflow, str(audio))

    assert info["artifact"]["media"]["duration"] > 0
    assert any(stream["type"] == "audio" for stream in info["artifact"]["media"]["streams"])


def test_video_metadata_is_read(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")
    work = tmp_path / "inspect_work"
    work.mkdir()
    video = work / "video.mp4"
    subprocess.run([
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=160x120:d=1",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=8000",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video),
    ], check=True)
    workflow = {"workflow_id": "inspect", "work_dir": str(work), "fixture_dir": str(work), "stages": []}

    info = runner.inspect_artifact(workflow, str(video))

    assert any(stream["type"] == "video" for stream in info["artifact"]["media"]["streams"])
    assert any(stream["type"] == "audio" for stream in info["artifact"]["media"]["streams"])


def test_subtitle_cue_preview_works(tmp_path):
    work = tmp_path / "inspect_work"
    work.mkdir()
    sub = work / "captions.srt"
    sub.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:01,000 --> 00:00:02,000\nWorld\n")
    workflow = {"workflow_id": "inspect", "work_dir": str(work), "fixture_dir": str(work), "stages": []}

    info = runner.inspect_artifact(workflow, str(sub))

    assert info["artifact"]["subtitle"]["cue_count"] == 2
    assert "Hello" in info["artifact"]["subtitle"]["preview"]


def test_lineage_reaches_final_artifact(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    lineage = runner.lineage_summary(result["workflow"])

    assert lineage["final_outputs"] == [str(tmp_path / "stage_review_work" / "final.mp4")]
    assert any(stage["stage_id"] == "export" for stage in lineage["stages"])


def test_path_traversal_and_unrelated_files_are_rejected(tmp_path):
    work = tmp_path / "inspect_work"
    work.mkdir()
    workflow = {"workflow_id": "inspect", "work_dir": str(work), "fixture_dir": str(work), "stages": []}

    with pytest.raises(RuntimeError, match="outside approved"):
        runner.inspect_artifact(workflow, "/etc/passwd")
    with pytest.raises(RuntimeError, match="outside approved"):
        runner.inspect_artifact(workflow, str(work / ".." / "other.txt"))


def test_inspection_does_not_approve_stage(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    runner.inspect_stage(result["workflow"], "segment_script", reviewer="Andrew")
    review = runner.load_review(result["workflow"])

    assert "segment_script" not in review.get("stage_reviews", {})
    assert review["stage_inspections"]["segment_script"][0]["inspected_by"] == "Andrew"


def test_changed_artifact_shows_fingerprint_mismatch(tmp_path, monkeypatch):
    install_fake_handlers(monkeypatch)
    manifest = make_stage_review_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    runner.record_stage_review_decision(result["workflow"], "segment_script", "approved", reviewer="Andrew")
    output = Path(runner.stage_map(result["workflow"])["segment_script"]["outputs"][0])
    output.write_text("changed\n")

    inspection = runner.inspect_stage(result["workflow"], "segment_script")

    assert inspection["fingerprints_match_review"] is False
    assert inspection["stage_review"]["state"] == "invalidated"


def test_explicit_open_is_separate_from_normal_inspection(tmp_path):
    work = tmp_path / "inspect_work"
    work.mkdir()
    text = work / "note.txt"
    text.write_text("hello\n")
    workflow = {"workflow_id": "inspect", "work_dir": str(work), "fixture_dir": str(work), "stages": []}

    info = runner.inspect_artifact(workflow, str(text), open_artifact=False)

    assert info["open"]["attempted"] is False


def test_scene_cards_handler_produces_valid_video(tmp_path):
    manifest = make_scene_cards_manifest(tmp_path)

    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    stage = runner.stage_map(result["workflow"])["generate_placeholder_visual"]
    meta = runner.artifact_metadata(result["workflow"], stage["outputs"][0])

    assert stage["status"] == "completed"
    assert stage["implementation"]["selected"] == "pillow_scene_cards"
    assert meta["media"]["duration"] > 0
    assert any(stream["type"] == "video" for stream in meta["media"]["streams"])
    assert stage["implementation"]["style_profile"] == "clean_default"
    assert stage["implementation"]["style_config_fingerprint"]["valid"] is True


def test_valid_style_file_renders_correctly(tmp_path):
    manifest = make_scene_cards_manifest(tmp_path, profile="technical_brief")

    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    stage = runner.stage_map(result["workflow"])["generate_placeholder_visual"]

    assert stage["status"] == "completed"
    assert stage["implementation"]["validated_configuration"]["background_mode"] == "solid"
    assert stage["implementation"]["style_profile"] == "technical_brief"


def test_invalid_color_or_dimensions_are_rejected(tmp_path):
    style = scene_card_style_data()
    style["profiles"]["clean_default"]["background_color"] = "blue"
    manifest = make_scene_cards_manifest(tmp_path, style_data=style)

    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    stage = runner.stage_map(result["workflow"])["generate_placeholder_visual"]

    assert stage["status"] == "failed"
    assert "invalid color format" in stage["error"]

    style = scene_card_style_data()
    style["profiles"]["clean_default"]["canvas_width"] = 20
    manifest = make_scene_cards_manifest(tmp_path / "bad_dimensions", style_data=style)

    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    stage = runner.stage_map(result["workflow"])["generate_placeholder_visual"]

    assert stage["status"] == "failed"
    assert "invalid canvas_width" in stage["error"]


def test_dense_text_splits_into_multiple_cards_without_truncation(tmp_path):
    dense = (
        "This workflow needs a dense explanation about intake validation, visual generation, captions, "
        "rendering, quality checks, review gates, artifact lineage, and resumable stage execution. "
        "Every phrase should remain represented instead of being silently cut from the rendered plan."
    )
    style = scene_card_style_data()
    style["profiles"]["clean_default"]["maximum_characters_per_card"] = 60
    manifest = make_scene_cards_manifest(tmp_path, style_data=style, script_text=dense)

    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    stage = runner.stage_map(result["workflow"])["generate_placeholder_visual"]
    decisions = stage["implementation"]["layout_decisions"]

    assert stage["implementation"]["card_count"] > stage["implementation"]["segment_count"]
    assert any(item["decision"] in {"split_by_character_limit", "split_to_preserve_text"} for item in decisions)


def test_minimum_font_size_is_respected(tmp_path):
    dense = " ".join(["workflowproof"] * 80)
    style = scene_card_style_data()
    style["profiles"]["clean_default"]["body_font_size"] = 24
    style["profiles"]["clean_default"]["minimum_font_size"] = 18
    style["profiles"]["clean_default"]["maximum_lines"] = 3
    style["profiles"]["clean_default"]["maximum_characters_per_card"] = 240
    manifest = make_scene_cards_manifest(tmp_path, style_data=style, script_text=dense)

    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    stage = runner.stage_map(result["workflow"])["generate_placeholder_visual"]

    assert all(card["to"] >= 18 for card in stage["implementation"]["layout_decisions"] if card["decision"] == "font_reduced")


def test_style_changes_invalidate_visual_and_downstream_only(tmp_path):
    manifest = make_scene_cards_manifest(tmp_path)
    first = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    visual_stage = runner.stage_map(first["workflow"])["generate_placeholder_visual"]
    style_path = Path(visual_stage["inputs"][1])
    style = json.loads(style_path.read_text())
    style["profiles"]["clean_default"]["accent_color"] = "#FFAA00"
    style_path.write_text(json.dumps(style))

    status = runner.run_workflow(manifest, status_only=True)
    statuses = {stage["stage_id"]: stage["status"] for stage in status["workflow"]["stages"]}

    assert statuses["intake"] == "completed"
    assert statuses["segment_script"] == "completed"
    assert statuses["generate_placeholder_audio"] == "completed"
    assert statuses["generate_placeholder_visual"] == "pending"
    assert statuses["assemble_video"] == "pending"
    assert statuses["quality_check"] == "pending"
    assert "generate_placeholder_visual" in status["invalidated"]


def test_style_unchanged_resume_skips_rendering(tmp_path):
    manifest = make_scene_cards_manifest(tmp_path)
    runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    resumed = runner.run_workflow(manifest, resume=True)

    assert all(item["status"] == "skipped" for item in resumed["executed"])


def test_placeholder_fallback_still_works(tmp_path):
    manifest = make_manifest(tmp_path)
    workflow = runner.load_workflow(manifest, prefer_runtime=False)
    stage = {"stage_id": "generate_placeholder_visual", "inputs": [], "outputs": [str(tmp_path / "visual.ppm")]}

    runner.handler_generate_placeholder_visual(workflow, stage)

    assert stage["status"] == "completed"
    assert Path(stage["outputs"][0]).exists()


def test_scene_card_defaults_work_without_style_file(tmp_path):
    manifest = make_scene_cards_manifest(tmp_path)
    data = json.loads(manifest.read_text())
    visual = data["stages"][3]
    visual["inputs"] = [visual["inputs"][0]]
    visual.pop("style_config_path")
    visual.pop("style_profile")
    manifest.write_text(json.dumps(data))

    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    stage = runner.stage_map(result["workflow"])["generate_placeholder_visual"]

    assert stage["status"] == "completed"
    assert stage["implementation"]["style_profile"] == "clean_default"


def test_font_path_restrictions_prevent_unrelated_access(tmp_path):
    style = scene_card_style_data()
    style["profiles"]["clean_default"]["font_path"] = "/etc/passwd"
    manifest = make_scene_cards_manifest(tmp_path, style_data=style)

    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    stage = runner.stage_map(result["workflow"])["generate_placeholder_visual"]

    assert stage["status"] == "failed"
    assert "font path outside approved directories" in stage["error"]


def test_all_three_fixture_profiles_produce_valid_media(tmp_path):
    for profile in ("clean_default", "technical_brief", "high_contrast"):
        manifest = make_scene_cards_manifest(tmp_path / profile, profile=profile)
        result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
        stage = runner.stage_map(result["workflow"])["generate_placeholder_visual"]
        meta = runner.artifact_metadata(result["workflow"], stage["outputs"][0])

        assert stage["status"] == "completed"
        assert stage["implementation"]["style_profile"] == profile
        assert any(stream["type"] == "video" for stream in meta["media"]["streams"])


def test_scene_cards_missing_dependency_falls_back_when_configured(tmp_path, monkeypatch):
    manifest = make_scene_cards_manifest(tmp_path)
    runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    workflow = runner.load_workflow(manifest)
    stage = runner.stage_map(workflow)["generate_placeholder_visual"]
    stage["outputs"] = [str(tmp_path / "fallback.ppm")]
    monkeypatch.setattr(runner, "tool_status", lambda: {"ffmpeg": None, "ffprobe": None, "espeak-ng": None})

    runner.handler_generate_scene_cards_visual(workflow, stage)

    assert stage["status"] == "completed"
    assert stage["implementation"]["selected"] == "placeholder_fallback"
    assert Path(stage["outputs"][0]).suffix == ".ppm"


def test_scene_cards_rerun_invalidates_only_visual_review(tmp_path):
    manifest = make_scene_cards_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)
    workflow = result["workflow"]
    approve_required_stages(workflow)
    runner.record_review_decision(workflow, "approved", reviewer="Andrew", confirm_approval=True)

    rerun = runner.run_workflow(manifest, retry_stage="generate_placeholder_visual")
    allowed, reasons = runner.can_proceed_to_external_adapter(rerun["workflow"])
    review = runner.load_review(rerun["workflow"])

    assert allowed is False
    assert review["stage_reviews"]["generate_placeholder_visual"]["decision"] == "invalidated"
    assert review["stage_reviews"]["segment_script"]["decision"] == "approved"
    assert any("generate_placeholder_visual" in reason for reason in reasons)


def test_scene_cards_lineage_records_selected_implementation(tmp_path):
    manifest = make_scene_cards_manifest(tmp_path)
    result = runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    lineage = runner.lineage_summary(result["workflow"])
    visual = next(stage for stage in lineage["stages"] if stage["stage_id"] == "generate_placeholder_visual")

    assert visual["handler"] == "generate_scene_cards_visual"
    assert visual["implementation"]["selected"] == "pillow_scene_cards"
    assert any(item["path"].endswith("scene_card_style.json") for item in visual["inputs"])


def test_scene_cards_resume_skips_valid_output(tmp_path):
    manifest = make_scene_cards_manifest(tmp_path)
    runner.run_workflow(manifest, execute=True, prefer_runtime=False)

    resumed = runner.run_workflow(manifest, resume=True)

    assert all(item["status"] == "skipped" for item in resumed["executed"])


def test_scene_cards_dry_run_reports_selected_implementation(tmp_path):
    manifest = make_scene_cards_manifest(tmp_path)

    result = runner.run_workflow(manifest, dry_run=True, prefer_runtime=False)
    visual = next(stage for stage in result["stages"] if stage["stage_id"] == "generate_placeholder_visual")

    assert visual["handler"] == "generate_scene_cards_visual"
    assert visual["implementation"]["selected"] == "generate_scene_cards_visual"
    assert visual["implementation"]["style_config_path"].endswith("scene_card_style.json")
    assert visual["implementation"]["style_profile"] == "clean_default"
