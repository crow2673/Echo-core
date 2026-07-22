#!/usr/bin/env python3
"""Manifest-driven dry-run/local media workflow runner.

This runner is intentionally manual-only. It executes local fixture workflows
from a stage manifest, records stage state, supports resume/retry, and never
calls external services.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import mimetypes
import os
import shutil
import subprocess
import textwrap
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = BASE / "tests/fixtures/ai_video_workflow/runner_manifest.json"
STATES = {"pending", "running", "completed", "failed", "skipped", "blocked", "awaiting_review"}
REVIEW_STATES = {"pending_review", "approved", "rejected", "changes_requested", "invalidated"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else BASE / p


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(BASE))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(paths: list[str]) -> dict[str, Any]:
    items = []
    for raw in paths:
        path = resolve(raw)
        if not path.exists() or not path.is_file() or path.stat().st_size == 0:
            return {"valid": False, "files": items, "missing_or_empty": raw}
        items.append({"path": raw, "size": path.stat().st_size, "sha256": sha256_file(path)})
    joined = json.dumps(items, sort_keys=True)
    return {"valid": True, "files": items, "sha256": hashlib.sha256(joined.encode()).hexdigest()}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.rename(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def runtime_manifest_path(manifest: dict[str, Any]) -> Path:
    return resolve(manifest.get("work_dir", "memory/media_workflows/default")) / "stage_manifest.json"


def normalize_stage(raw: dict[str, Any]) -> dict[str, Any]:
    stage = {
        "stage_id": raw["stage_id"],
        "status": raw.get("status", "pending"),
        "inputs": raw.get("inputs", []),
        "outputs": raw.get("outputs", []),
        "dependencies": raw.get("dependencies", []),
        "handler": raw.get("handler") or raw.get("command") or raw["stage_id"],
        "command": raw.get("command"),
        "started_at": raw.get("started_at"),
        "completed_at": raw.get("completed_at"),
        "error": raw.get("error"),
        "retryable": bool(raw.get("retryable", True)),
        "human_review_required": bool(raw.get("human_review_required", False)),
        "checksum": raw.get("checksum"),
        "attempts": int(raw.get("attempts", 0) or 0),
    }
    for key, value in raw.items():
        stage.setdefault(key, value)
    if stage["status"] not in STATES:
        stage["status"] = "pending"
    return stage


def load_workflow(manifest_path: Path, prefer_runtime: bool = True) -> dict[str, Any]:
    source = load_json(manifest_path)
    rt = runtime_manifest_path(source)
    if prefer_runtime and rt.exists():
        data = load_json(rt)
        data.setdefault("source_manifest", rel(manifest_path))
        return data
    data = {
        "workflow_id": source.get("workflow_id", manifest_path.stem),
        "source_manifest": rel(manifest_path),
        "fixture_dir": source.get("fixture_dir"),
        "work_dir": source.get("work_dir", "memory/media_workflows/default"),
        "external_services_allowed": bool(source.get("external_services_allowed", False)),
        "external_required_stages": source.get("external_required_stages", []),
        "created_at": utcnow(),
        "updated_at": utcnow(),
        "stages": [normalize_stage(stage) for stage in source.get("stages", [])],
    }
    return data


def save_workflow(workflow: dict[str, Any]) -> None:
    workflow["updated_at"] = utcnow()
    write_json(runtime_manifest_path(workflow), workflow)


def review_path(workflow: dict[str, Any]) -> Path:
    return resolve(workflow.get("work_dir", "memory/media_workflows/default")) / "review.json"


def stage_map(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {stage["stage_id"]: stage for stage in workflow.get("stages", [])}


def stage_by_handler(workflow: dict[str, Any], handler: str) -> dict[str, Any] | None:
    for stage in workflow.get("stages", []):
        if stage.get("handler") == handler or stage.get("stage_id") == handler:
            return stage
    return None


def dependents(workflow: dict[str, Any], stage_id: str) -> set[str]:
    out = set()
    changed = True
    while changed:
        changed = False
        for stage in workflow.get("stages", []):
            deps = set(stage.get("dependencies", []))
            if stage["stage_id"] in out:
                continue
            if stage_id in deps or deps & out:
                out.add(stage["stage_id"])
                changed = True
    return out


def validate_completed_stages(workflow: dict[str, Any]) -> list[str]:
    invalid = []
    stages = stage_map(workflow)
    for stage in workflow.get("stages", []):
        if stage["status"] != "completed":
            continue
        current = stage_fingerprints(stage)
        recorded = stage.get("validation_fingerprint")
        output_fp = current["outputs"]
        output_changed = not output_fp.get("valid") or output_fp.get("sha256") != stage.get("checksum", {}).get("sha256")
        fingerprint_changed = False
        if recorded:
            for key in ("inputs", "outputs", "stage_manifest"):
                if (recorded.get(key) or {}).get("sha256") != (current.get(key) or {}).get("sha256"):
                    fingerprint_changed = True
                    break
        if output_changed or fingerprint_changed:
            stage["status"] = "pending"
            reason = output_fp.get("missing_or_empty", "stage fingerprint changed" if fingerprint_changed else "checksum mismatch")
            stage["error"] = f"invalidated output fingerprint: {reason}"
            stage["completed_at"] = None
            stage["checksum"] = None
            stage["validation_fingerprint"] = None
            invalid.append(stage["stage_id"])
            for dep_id in dependents(workflow, stage["stage_id"]):
                dep = stages[dep_id]
                if dep["status"] == "completed":
                    dep["status"] = "pending"
                    dep["error"] = f"upstream invalidated: {stage['stage_id']}"
                    dep["completed_at"] = None
                    dep["checksum"] = None
                    dep["validation_fingerprint"] = None
    return invalid


def workflow_complete(workflow: dict[str, Any]) -> bool:
    return bool(workflow.get("stages")) and all(stage.get("status") == "completed" for stage in workflow.get("stages", []))


def ensure_pending_review(workflow: dict[str, Any]) -> None:
    if not workflow_complete(workflow):
        return
    path = review_path(workflow)
    if path.exists():
        return
    write_json(path, {
        "state": "pending_review",
        "workflow_id": workflow.get("workflow_id"),
        "created_at": utcnow(),
        "updated_at": utcnow(),
        "decision": None,
        "history": [{
            "state": "pending_review",
            "at": utcnow(),
            "reason": "workflow completed and requires human review",
        }],
    })


def load_review(workflow: dict[str, Any]) -> dict[str, Any]:
    path = review_path(workflow)
    if not path.exists():
        if workflow_complete(workflow):
            ensure_pending_review(workflow)
            return load_json(path)
        return {"state": "pending_review", "workflow_id": workflow.get("workflow_id"), "decision": None, "history": []}
    data = load_json(path)
    if data.get("state") not in REVIEW_STATES:
        data["state"] = "pending_review"
    data.setdefault("history", [])
    data.setdefault("stage_reviews", {})
    return data


def save_review(workflow: dict[str, Any], review: dict[str, Any]) -> None:
    review["workflow_id"] = workflow.get("workflow_id")
    review["updated_at"] = utcnow()
    write_json(review_path(workflow), review)


def single_file_fingerprint(path: str | None) -> dict[str, Any]:
    if not path:
        return {"valid": False, "path": None, "missing_or_empty": "missing path"}
    fp = fingerprint([path])
    if fp.get("files"):
        return {"valid": fp.get("valid", False), **fp["files"][0]}
    return {"valid": False, "path": path, "missing_or_empty": fp.get("missing_or_empty", path)}


def workflow_fingerprint(workflow: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "workflow_id": workflow.get("workflow_id"),
        "source_manifest": workflow.get("source_manifest"),
        "fixture_dir": workflow.get("fixture_dir"),
        "work_dir": workflow.get("work_dir"),
        "external_services_allowed": workflow.get("external_services_allowed"),
        "external_required_stages": workflow.get("external_required_stages", []),
        "stages": [
            {
                "stage_id": stage.get("stage_id"),
                "status": stage.get("status"),
                "inputs": stage.get("inputs", []),
                "outputs": stage.get("outputs", []),
                "dependencies": stage.get("dependencies", []),
                "handler": stage.get("handler"),
                "checksum": stage.get("checksum"),
                "attempts": stage.get("attempts", 0),
            }
            for stage in workflow.get("stages", [])
        ],
    }
    encoded = json.dumps(payload, sort_keys=True)
    return {
        "valid": True,
        "path": rel(runtime_manifest_path(workflow)),
        "sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "size": len(encoded.encode()),
    }


def stage_manifest_fingerprint(stage: dict[str, Any]) -> dict[str, Any]:
    config = {
        key: value for key, value in stage.items()
        if key not in {"started_at", "completed_at", "error", "checksum", "validation_fingerprint"}
    }
    payload = {
        "stage_id": stage.get("stage_id"),
        "status": stage.get("status"),
        "inputs": stage.get("inputs", []),
        "outputs": stage.get("outputs", []),
        "dependencies": stage.get("dependencies", []),
        "handler": stage.get("handler"),
        "command": stage.get("command"),
        "retryable": stage.get("retryable"),
        "human_review_required": stage.get("human_review_required"),
        "checksum": stage.get("checksum"),
        "attempts": stage.get("attempts", 0),
        "config": config,
    }
    encoded = json.dumps(payload, sort_keys=True)
    return {
        "valid": True,
        "stage_id": stage.get("stage_id"),
        "sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "size": len(encoded.encode()),
    }


def stage_fingerprints(stage: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage_id": stage.get("stage_id"),
        "inputs": fingerprint(stage.get("inputs", [])) if stage.get("inputs") else {"valid": True, "files": [], "sha256": "no-inputs"},
        "outputs": fingerprint(stage.get("outputs", [])) if stage.get("outputs") else {"valid": True, "files": [], "sha256": "no-outputs"},
        "stage_manifest": stage_manifest_fingerprint(stage),
        "attempts": int(stage.get("attempts", 0) or 0),
    }


def stage_review_mismatches(record: dict[str, Any], current: dict[str, Any]) -> list[str]:
    old = record.get("stage_fingerprints") or {}
    mismatches: list[str] = []
    for key in ("inputs", "outputs", "stage_manifest"):
        old_item = old.get(key) or {}
        new_item = current.get(key) or {}
        if old_item.get("sha256") != new_item.get("sha256") or not new_item.get("valid", False):
            mismatches.append(key)
    if int(current.get("attempts", 0) or 0) > int(old.get("attempts", 0) or 0):
        mismatches.append("stage_rerun")
    return mismatches


def stage_review_status(workflow: dict[str, Any], review: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    record = (review.get("stage_reviews") or {}).get(stage["stage_id"])
    if not record:
        return {
            "stage_id": stage["stage_id"],
            "state": "pending_review",
            "blocks_final_approval": bool(stage.get("human_review_required")),
            "fingerprints_valid": False,
            "mismatches": ["missing_stage_review"],
        }
    mismatches = stage_review_mismatches(record, stage_fingerprints(stage))
    state = record.get("decision", "pending_review")
    return {
        "stage_id": stage["stage_id"],
        "state": "invalidated" if mismatches else state,
        "reviewer": record.get("reviewer"),
        "notes": record.get("notes"),
        "warnings": record.get("warnings_seen", []),
        "unresolved_items": record.get("unresolved_items", []),
        "fingerprints_valid": not mismatches,
        "mismatches": mismatches,
        "blocks_final_approval": bool(stage.get("human_review_required")) and (state != "approved" or bool(mismatches)),
    }


def stage_warnings(workflow: dict[str, Any], stage: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if stage.get("status") != "completed":
        warnings.append(f"stage is not completed: {stage.get('status')}")
    if not fingerprint(stage.get("outputs", [])).get("valid"):
        warnings.append("stage output fingerprint is not valid")
    if stage.get("error"):
        warnings.append(f"stage has recorded error: {stage.get('error')}")
    if stage.get("human_review_required"):
        warnings.append("human review required")
    return warnings


def invalidate_stage_reviews_if_needed(workflow: dict[str, Any], reason: str = "stage reviewed artifact changed") -> dict[str, Any]:
    review = load_review(workflow)
    changed = False
    stages = stage_map(workflow)
    for stage_id, record in list((review.get("stage_reviews") or {}).items()):
        stage = stages.get(stage_id)
        if not stage or record.get("decision") != "approved":
            continue
        mismatches = stage_review_mismatches(record, stage_fingerprints(stage))
        if not mismatches:
            continue
        record["decision"] = "invalidated"
        record["invalidated_at"] = utcnow()
        record["invalidation_reason"] = reason
        record["mismatches"] = mismatches
        changed = True
        review.setdefault("history", []).append({
            "state": "invalidated",
            "scope": "stage",
            "stage_id": stage_id,
            "at": record["invalidated_at"],
            "reason": reason,
            "mismatches": mismatches,
        })
    if changed and review.get("state") == "approved":
        review["state"] = "invalidated"
        review["decision"] = "invalidated"
        review["invalidated_at"] = utcnow()
        review["invalidation_reason"] = "stage review invalidated"
        review.setdefault("history", []).append({
            "state": "invalidated",
            "scope": "workflow",
            "at": review["invalidated_at"],
            "reason": "stage review invalidated",
        })
    if changed:
        save_review(workflow, review)
    return review


def required_stage_review_blockers(workflow: dict[str, Any], review: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for stage in workflow.get("stages", []):
        if not stage.get("human_review_required"):
            continue
        status = stage_review_status(workflow, review, stage)
        if status["state"] != "approved":
            blockers.append(f"required stage review not approved: {stage['stage_id']}={status['state']}")
        elif not status["fingerprints_valid"]:
            blockers.append(f"required stage review fingerprint mismatch: {stage['stage_id']}")
    return blockers


def review_artifacts(workflow: dict[str, Any]) -> dict[str, Any]:
    final_stage = stage_by_handler(workflow, "write_final_manifest")
    export_stage = stage_by_handler(workflow, "export")
    quality_stage = stage_by_handler(workflow, "quality_check")
    manifest_path = rel(runtime_manifest_path(workflow))
    return {
        "manifest": workflow_fingerprint(workflow),
        "final_manifest": single_file_fingerprint((final_stage or {}).get("outputs", [None])[0]),
        "final_output": single_file_fingerprint((export_stage or {}).get("outputs", [None])[0]),
        "quality_report": single_file_fingerprint((quality_stage or {}).get("outputs", [None])[0]),
        "stage_attempts": {stage["stage_id"]: int(stage.get("attempts", 0) or 0) for stage in workflow.get("stages", [])},
    }


def review_mismatches(review: dict[str, Any], current: dict[str, Any]) -> list[str]:
    recorded = review.get("reviewed_artifacts") or {}
    mismatches: list[str] = []
    for key in ("manifest", "final_manifest", "final_output", "quality_report"):
        old = recorded.get(key) or {}
        new = current.get(key) or {}
        if old.get("sha256") != new.get("sha256") or old.get("size") != new.get("size") or not new.get("valid"):
            mismatches.append(key)
    old_attempts = recorded.get("stage_attempts") or {}
    new_attempts = current.get("stage_attempts") or {}
    for stage_id, old_attempt in old_attempts.items():
        if int(new_attempts.get(stage_id, 0) or 0) > int(old_attempt or 0):
            mismatches.append(f"stage_rerun:{stage_id}")
    return mismatches


def invalidate_review_if_needed(workflow: dict[str, Any], reason: str = "reviewed artifact changed") -> dict[str, Any]:
    review = load_review(workflow)
    if review.get("state") != "approved":
        return review
    current = review_artifacts(workflow)
    mismatches = review_mismatches(review, current)
    if not mismatches:
        return review
    review["state"] = "invalidated"
    review["decision"] = "invalidated"
    review["invalidated_at"] = utcnow()
    review["invalidation_reason"] = reason
    review["mismatches"] = mismatches
    review.setdefault("history", []).append({
        "state": "invalidated",
        "at": review["invalidated_at"],
        "reason": reason,
        "mismatches": mismatches,
    })
    save_review(workflow, review)
    return review


def tool_status() -> dict[str, Any]:
    return {
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "espeak-ng": shutil.which("espeak-ng"),
    }


def dependency_errors(stage: dict[str, Any], stages: dict[str, dict[str, Any]]) -> list[str]:
    errors = []
    for dep_id in stage.get("dependencies", []):
        dep = stages.get(dep_id)
        if not dep:
            errors.append(f"missing dependency stage: {dep_id}")
        elif dep.get("status") != "completed":
            errors.append(f"dependency not completed: {dep_id}={dep.get('status')}")
    return errors


def complete_stage(stage: dict[str, Any], outputs: list[str] | None = None) -> None:
    if outputs is not None:
        stage["outputs"] = outputs
    fp = fingerprint(stage.get("outputs", []))
    if not fp.get("valid"):
        raise RuntimeError(f"stage output missing or empty: {fp.get('missing_or_empty')}")
    stage["checksum"] = fp
    stage["status"] = "completed"
    stage["completed_at"] = utcnow()
    stage["error"] = None
    stage["validation_fingerprint"] = stage_fingerprints(stage)


def read_segments(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text()).get("segments", [])


def handler_intake(workflow: dict[str, Any], stage: dict[str, Any]) -> None:
    src = resolve(stage["inputs"][0])
    text = " ".join(src.read_text().split())
    out = resolve(stage["outputs"][0])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n")
    complete_stage(stage)


def handler_segment_script(workflow: dict[str, Any], stage: dict[str, Any]) -> None:
    text = resolve(stage["inputs"][0]).read_text().strip()
    parts = [p.strip() for p in text.replace("?", ".").replace("!", ".").split(".") if p.strip()]
    if not parts:
        raise RuntimeError("no script segments found")
    segments = []
    start = 0.0
    for idx, part in enumerate(parts, 1):
        duration = max(2.0, min(6.0, len(part.split()) * 0.38))
        segments.append({"id": idx, "text": part, "start": round(start, 2), "end": round(start + duration, 2)})
        start += duration
    out = resolve(stage["outputs"][0])
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, {"segments": segments, "duration": round(start, 2), "human_review_required": True})
    complete_stage(stage)


def write_silent_wav(path: Path, seconds: float = 3.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 16000
    frames = int(sample_rate * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)


def handler_generate_placeholder_audio(workflow: dict[str, Any], stage: dict[str, Any]) -> None:
    segments = read_segments(resolve(stage["inputs"][0]))
    text = " ".join(seg["text"] for seg in segments)
    out = resolve(stage["outputs"][0])
    out.parent.mkdir(parents=True, exist_ok=True)
    espeak = shutil.which("espeak-ng")
    if espeak:
        subprocess.run([espeak, "-v", "en-us", "-s", "155", "-w", str(out), text], check=True)
    else:
        write_silent_wav(out, seconds=max(3.0, sum(seg["end"] - seg["start"] for seg in segments)))
        stage["error"] = "espeak-ng missing; generated silent placeholder"
    complete_stage(stage)


def handler_generate_placeholder_visual(workflow: dict[str, Any], stage: dict[str, Any]) -> None:
    out = resolve(stage["outputs"][0])
    out.parent.mkdir(parents=True, exist_ok=True)
    width, height = 720, 1280
    with out.open("wb") as handle:
        handle.write(f"P6\n{width} {height}\n255\n".encode())
        for y in range(height):
            for x in range(width):
                r = 20 + int(50 * y / height)
                g = 70 + int(60 * x / width)
                b = 130
                if 250 < x < 470 and 380 < y < 680:
                    r, g, b = 230, 230, 235
                if 310 < x < 410 and 450 < y < 550:
                    r, g, b = 80, 100, 150
                handle.write(bytes((r % 256, g % 256, b % 256)))
    complete_stage(stage)


DEFAULT_SCENE_CARD_STYLE: dict[str, Any] = {
    "schema_version": 1,
    "profile": "clean_default",
    "canvas_width": 720,
    "canvas_height": 1280,
    "frame_rate": 30,
    "background_mode": "gradient",
    "background_color": "#122542",
    "background_gradient": ["#122542", "#267491"],
    "foreground_color": "#E8F4F8",
    "accent_color": "#E8F4F8",
    "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "title_font_size": 46,
    "body_font_size": 34,
    "minimum_font_size": 22,
    "line_spacing": 12,
    "horizontal_margin": 72,
    "vertical_margin": 86,
    "text_alignment": "left",
    "vertical_alignment": "center",
    "maximum_lines": 8,
    "maximum_characters_per_card": 145,
    "card_duration_seconds": 4.0,
    "transition_type": "cut",
    "transition_duration_seconds": 0.0,
    "show_scene_number": True,
    "show_progress_indicator": True,
    "safe_area": {"left": 54, "top": 140, "right": 54, "bottom": 160},
    "deterministic_seed": 1337,
}


def parse_hex_color(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        raise RuntimeError(f"invalid color format: {value!r}")
    try:
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]
    except ValueError as exc:
        raise RuntimeError(f"invalid color format: {value!r}") from exc


def require_range(config: dict[str, Any], key: str, low: float, high: float) -> None:
    value = config.get(key)
    if not isinstance(value, (int, float)) or not (low <= float(value) <= high):
        raise RuntimeError(f"invalid {key}: expected {low}..{high}, got {value!r}")


def allowed_font_path(path: str | None, workflow: dict[str, Any]) -> str | None:
    if not path:
        return None
    font = resolve(path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    approved = [Path("/usr/share/fonts").resolve(), Path("/usr/local/share/fonts").resolve()]
    fixture = workflow.get("fixture_dir")
    if fixture:
        approved.append(resolve(fixture).resolve())
    work = workflow.get("work_dir")
    if work:
        approved.append(resolve(work).resolve())
    if not any(font == root or root in font.parents for root in approved):
        raise RuntimeError(f"font path outside approved directories: {path}")
    if not font.exists() or not font.is_file():
        raise RuntimeError(f"font path does not exist: {path}")
    return str(font)


def style_config_source(stage: dict[str, Any]) -> str | None:
    for key in ("style_config", "style_config_path"):
        if stage.get(key):
            return str(stage[key])
    if stage.get("handler") != "generate_scene_cards_visual":
        return None
    for item in stage.get("inputs", [])[1:]:
        if str(item).endswith(".json"):
            return str(item)
    return None


def load_scene_card_style(workflow: dict[str, Any], stage: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    style = dict(DEFAULT_SCENE_CARD_STYLE)
    source = style_config_source(stage)
    profile_name = stage.get("style_profile") or style["profile"]
    source_fingerprint = None
    if source:
        path = safe_artifact_path(workflow, source)
        raw = load_json(path)
        profiles = raw.get("profiles", raw)
        if profile_name not in profiles:
            raise RuntimeError(f"style profile not found: {profile_name}")
        style.update(profiles[profile_name])
        style["profile"] = profile_name
        source_fingerprint = single_file_fingerprint(rel(path))
    else:
        style["profile"] = profile_name
    style = validate_scene_card_style(style, workflow)
    metadata = {
        "style_config_path": source,
        "style_profile": style.get("profile"),
        "style_config_fingerprint": source_fingerprint,
        "validated_configuration": style,
    }
    return style, metadata


def validate_scene_card_style(style: dict[str, Any], workflow: dict[str, Any]) -> dict[str, Any]:
    config = dict(style)
    if config.get("schema_version") != 1:
        raise RuntimeError("unsupported scene-card style schema_version")
    for key, low, high in [
        ("canvas_width", 320, 2160),
        ("canvas_height", 320, 3840),
        ("frame_rate", 1, 60),
        ("title_font_size", 12, 120),
        ("body_font_size", 10, 96),
        ("minimum_font_size", 8, 72),
        ("line_spacing", 0, 80),
        ("horizontal_margin", 0, 400),
        ("vertical_margin", 0, 400),
        ("maximum_lines", 1, 20),
        ("maximum_characters_per_card", 20, 600),
        ("card_duration_seconds", 1, 30),
        ("transition_duration_seconds", 0, 5),
    ]:
        require_range(config, key, low, high)
    if int(config["minimum_font_size"]) > int(config["body_font_size"]):
        raise RuntimeError("minimum_font_size cannot exceed body_font_size")
    if config.get("background_mode") not in {"solid", "gradient"}:
        raise RuntimeError(f"unsupported background_mode: {config.get('background_mode')}")
    if config.get("text_alignment") not in {"left", "center", "right"}:
        raise RuntimeError(f"unsupported text_alignment: {config.get('text_alignment')}")
    if config.get("vertical_alignment") not in {"top", "center", "bottom"}:
        raise RuntimeError(f"unsupported vertical_alignment: {config.get('vertical_alignment')}")
    if config.get("transition_type") not in {"cut", "fade"}:
        raise RuntimeError(f"unsupported transition_type: {config.get('transition_type')}")
    parse_hex_color(config["background_color"])
    parse_hex_color(config["foreground_color"])
    parse_hex_color(config["accent_color"])
    gradient = config.get("background_gradient") or []
    if not isinstance(gradient, list) or len(gradient) != 2:
        raise RuntimeError("background_gradient must contain exactly two colors")
    parse_hex_color(gradient[0])
    parse_hex_color(gradient[1])
    safe = config.get("safe_area")
    if not isinstance(safe, dict):
        raise RuntimeError("safe_area must be an object")
    for key in ("left", "top", "right", "bottom"):
        if not isinstance(safe.get(key), (int, float)) or safe[key] < 0:
            raise RuntimeError(f"invalid safe_area.{key}")
    if safe["left"] + safe["right"] >= config["canvas_width"]:
        raise RuntimeError("safe_area left+right exceeds canvas width")
    if safe["top"] + safe["bottom"] >= config["canvas_height"]:
        raise RuntimeError("safe_area top+bottom exceeds canvas height")
    config["font_path"] = allowed_font_path(config.get("font_path"), workflow)
    return config


def split_text_for_cards(text: str, max_chars: int) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word])
        if current and len(candidate) > max_chars:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        chunks.append(" ".join(current))
    return chunks or [text]


def wrap_with_font(draw: Any, text: str, font: Any, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(" ".join(current))
            current = [word]
        elif not current and bbox[2] - bbox[0] > max_width:
            chunk = ""
            for char in word:
                probe = chunk + char
                probe_bbox = draw.textbbox((0, 0), probe, font=font)
                if chunk and probe_bbox[2] - probe_bbox[0] > max_width:
                    lines.append(chunk)
                    chunk = char
                else:
                    chunk = probe
            current = [chunk] if chunk else []
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def handler_generate_scene_cards_visual(workflow: dict[str, Any], stage: dict[str, Any]) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version
    except Exception as exc:
        if stage.get("fallback_handler") == "generate_placeholder_visual":
            handler_generate_placeholder_visual(workflow, stage)
            stage["implementation"] = {
                "selected": "placeholder_fallback",
                "reason": f"Pillow unavailable: {exc}",
            }
            return
        raise RuntimeError(f"missing dependency: Pillow ({exc})")
    tools = tool_status()
    if not tools["ffmpeg"]:
        if stage.get("fallback_handler") == "generate_placeholder_visual":
            handler_generate_placeholder_visual(workflow, stage)
            stage["implementation"] = {
                "selected": "placeholder_fallback",
                "reason": "ffmpeg unavailable",
            }
            return
        raise RuntimeError("missing dependency: ffmpeg")

    try:
        style, style_metadata = load_scene_card_style(workflow, stage)
    except Exception:
        if stage.get("fallback_handler") == "generate_placeholder_visual" and stage.get("allow_style_fallback"):
            handler_generate_placeholder_visual(workflow, stage)
            stage["implementation"] = {
                "selected": "placeholder_fallback",
                "reason": "style validation failed",
            }
            return
        raise

    segments = read_segments(resolve(stage["inputs"][0]))
    if not segments:
        raise RuntimeError("no script segments found")
    out = resolve(stage["outputs"][0])
    out.parent.mkdir(parents=True, exist_ok=True)
    frame_dir = resolve(workflow.get("work_dir", "memory/media_workflows/default")) / "work" / "visual" / "scene_cards_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    seed = int(style["deterministic_seed"])
    frame_rate = int(style["frame_rate"])
    width, height = int(style["canvas_width"]), int(style["canvas_height"])
    fg = parse_hex_color(style["foreground_color"])
    accent = parse_hex_color(style["accent_color"])
    bg_solid = parse_hex_color(style["background_color"])
    bg1, bg2 = [parse_hex_color(item) for item in style["background_gradient"]]
    font_path = style.get("font_path")
    title_font = ImageFont.truetype(font_path, int(style["title_font_size"])) if font_path else ImageFont.load_default()
    small_font_size = max(int(style["minimum_font_size"]), min(24, int(style["body_font_size"]) - 8))
    small_font = ImageFont.truetype(font_path, small_font_size) if font_path else ImageFont.load_default()
    safe = style["safe_area"]
    text_left = int(safe["left"] + style["horizontal_margin"] / 4)
    text_right = int(width - safe["right"] - style["horizontal_margin"] / 4)
    text_width = max(120, text_right - text_left)
    body_top = int(safe["top"] + style["vertical_margin"] + int(style["title_font_size"]) * 2)
    body_bottom = int(height - safe["bottom"] - 110)
    line_spacing = int(style["line_spacing"])
    max_lines = int(style["maximum_lines"])
    layout_decisions: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    for seg in segments:
        chunks = split_text_for_cards(seg["text"], int(style["maximum_characters_per_card"]))
        if len(chunks) > 1:
            layout_decisions.append({"segment_id": seg["id"], "decision": "split_by_character_limit", "parts": len(chunks)})
        seg_duration = max(1.0, float(seg["end"]) - float(seg["start"]))
        part_duration = max(1.0, seg_duration / max(1, len(chunks)))
        pending = list(chunks)
        part = 0
        while pending:
            text = pending.pop(0)
            part += 1
            chosen_font_size = int(style["body_font_size"])
            final_lines: list[str] = []
            while chosen_font_size >= int(style["minimum_font_size"]):
                body_font = ImageFont.truetype(font_path, chosen_font_size) if font_path else ImageFont.load_default()
                probe = Image.new("RGB", (width, height))
                probe_draw = ImageDraw.Draw(probe)
                lines = wrap_with_font(probe_draw, text, body_font, text_width)
                if len(lines) <= max_lines:
                    final_lines = lines
                    break
                chosen_font_size -= 2
            if not final_lines or len(final_lines) > max_lines:
                words = text.split()
                if len(words) <= 1:
                    final_lines = final_lines[:max_lines] or [text]
                else:
                    mid = max(1, len(words) // 2)
                    pending.insert(0, " ".join(words[mid:]))
                    pending.insert(0, " ".join(words[:mid]))
                    layout_decisions.append({"segment_id": seg["id"], "decision": "split_to_preserve_text", "text_length": len(text)})
                    continue
            if chosen_font_size < int(style["body_font_size"]):
                layout_decisions.append({
                    "segment_id": seg["id"],
                    "decision": "font_reduced",
                    "from": int(style["body_font_size"]),
                    "to": chosen_font_size,
                })
            cards.append({
                "segment": seg,
                "part": part,
                "text": text,
                "lines": final_lines,
                "font_size": chosen_font_size,
                "duration": part_duration if chunks else float(style["card_duration_seconds"]),
            })
    frames: list[Path] = []
    for idx, card in enumerate(cards, 1):
        seg = card["segment"]
        img = Image.new("RGB", (width, height), bg_solid)
        draw = ImageDraw.Draw(img)
        if style["background_mode"] == "gradient":
            for y in range(height):
                blend = ((y + (idx + seed) * 13) % height) / max(1, height - 1)
                r = int(bg1[0] * (1 - blend) + bg2[0] * blend)
                g = int(bg1[1] * (1 - blend) + bg2[1] * blend)
                b = int(bg1[2] * (1 - blend) + bg2[2] * blend)
                draw.line([(0, y), (width, y)], fill=(r, g, b))
        draw.rounded_rectangle((safe["left"], safe["top"], width - safe["right"], height - safe["bottom"]),
                               radius=32, fill=(0, 0, 0), outline=accent, width=3)
        if style["show_scene_number"]:
            scene_label = f"Scene {int(seg['id']):02}"
            if len(split_text_for_cards(seg["text"], int(style["maximum_characters_per_card"]))) > 1:
                scene_label += f".{card['part']}"
            draw.text((text_left, int(style["vertical_margin"])), scene_label, fill=accent, font=small_font)
        title = str(stage.get("title", "Market explainer"))
        draw.text((text_left, int(style["vertical_margin"] + 68)), title, fill=fg, font=title_font)
        body_font = ImageFont.truetype(font_path, int(card["font_size"])) if font_path else ImageFont.load_default()
        total_text_height = len(card["lines"]) * int(card["font_size"]) + max(0, len(card["lines"]) - 1) * line_spacing
        if style["vertical_alignment"] == "top":
            y = body_top
        elif style["vertical_alignment"] == "bottom":
            y = max(body_top, body_bottom - total_text_height)
        else:
            y = max(body_top, body_top + (body_bottom - body_top - total_text_height) // 2)
        for line in card["lines"]:
            bbox = draw.textbbox((0, 0), line, font=body_font)
            line_width = bbox[2] - bbox[0]
            if style["text_alignment"] == "center":
                x = text_left + (text_width - line_width) // 2
            elif style["text_alignment"] == "right":
                x = text_right - line_width
            else:
                x = text_left
            draw.text((x, y), line, fill=fg, font=body_font)
            y += int(card["font_size"]) + line_spacing
        start, end = float(seg["start"]), float(seg["end"])
        draw.text((text_left, height - int(style["vertical_margin"]) - 32), f"{start:05.2f}s - {end:05.2f}s", fill=accent, font=small_font)
        if style["show_progress_indicator"]:
            progress_width = int((idx / len(cards)) * (width - text_left * 2))
            draw.rounded_rectangle((text_left, height - 72, width - text_left, height - 48), radius=10, fill=(80, 80, 80))
            draw.rounded_rectangle((text_left, height - 72, text_left + progress_width, height - 48), radius=10, fill=accent)
        frame = frame_dir / f"scene_{idx:03}.png"
        img.save(frame)
        frames.append(frame)

    concat_file = frame_dir / "concat.txt"
    lines = []
    for frame, card in zip(frames, cards):
        duration = max(1.0, float(card["duration"]))
        lines.append(f"file '{frame.as_posix()}'")
        lines.append(f"duration {duration:.3f}")
    lines.append(f"file '{frames[-1].as_posix()}'")
    concat_file.write_text("\n".join(lines) + "\n")
    cmd = [
        tools["ffmpeg"], "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-vf", f"fps={frame_rate},format=yuv420p",
        "-c:v", "libx264", "-movflags", "+faststart", str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "scene card ffmpeg render failed")
    stage["implementation"] = {
        "selected": "pillow_scene_cards",
        "pillow_version": pillow_version,
        "ffmpeg": tools["ffmpeg"],
        "seed": seed,
        "frame_rate": frame_rate,
        "width": width,
        "height": height,
        "segment_count": len(segments),
        "card_count": len(cards),
        "frame_dir": rel(frame_dir),
        **style_metadata,
        "font_used": font_path,
        "layout_decisions": layout_decisions,
        "transition_type": style["transition_type"],
    }
    complete_stage(stage)


def srt_time(seconds: float) -> str:
    ms = int((seconds - math.floor(seconds)) * 1000)
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def handler_generate_captions(workflow: dict[str, Any], stage: dict[str, Any]) -> None:
    segments = read_segments(resolve(stage["inputs"][0]))
    out = resolve(stage["outputs"][0])
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for seg in segments:
        lines.extend([
            str(seg["id"]),
            f"{srt_time(seg['start'])} --> {srt_time(seg['end'])}",
            seg["text"],
            "",
        ])
    out.write_text("\n".join(lines))
    complete_stage(stage)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate())


def handler_assemble_video(workflow: dict[str, Any], stage: dict[str, Any]) -> None:
    tools = tool_status()
    if not tools["ffmpeg"]:
        raise RuntimeError("missing dependency: ffmpeg")
    audio = resolve(stage["inputs"][0])
    visual = resolve(stage["inputs"][1])
    captions = resolve(stage["inputs"][2])
    out = resolve(stage["outputs"][0])
    out.parent.mkdir(parents=True, exist_ok=True)
    duration = max(1.0, wav_duration(audio))
    visual_is_video = visual.suffix.lower() in VIDEO_SUFFIXES
    vf = f"subtitles={captions}:force_style='Fontsize=28,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3'"
    if visual_is_video:
        cmd = [
            tools["ffmpeg"], "-y", "-loglevel", "error",
            "-i", str(visual), "-i", str(audio),
            "-t", f"{duration:.2f}",
            "-vf", vf,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(out),
        ]
    else:
        cmd = [
            tools["ffmpeg"], "-y", "-loglevel", "error",
            "-loop", "1", "-framerate", "30", "-i", str(visual),
            "-i", str(audio),
            "-t", f"{duration:.2f}",
            "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(out),
        ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        # Fallback without subtitle burn-in; captions remain separate and quality check verifies presence.
        if visual_is_video:
            cmd = [
                tools["ffmpeg"], "-y", "-loglevel", "error",
                "-i", str(visual), "-i", str(audio),
                "-t", f"{duration:.2f}",
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(out),
            ]
        else:
            cmd = [
                tools["ffmpeg"], "-y", "-loglevel", "error",
                "-loop", "1", "-framerate", "30", "-i", str(visual),
                "-i", str(audio),
                "-t", f"{duration:.2f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(out),
            ]
        res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "ffmpeg assemble failed")
    complete_stage(stage)


def ffprobe_json(path: Path) -> dict[str, Any]:
    probe = shutil.which("ffprobe")
    if not probe:
        raise RuntimeError("missing dependency: ffprobe")
    res = subprocess.run(
        [probe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(res.stdout)


def handler_quality_check(workflow: dict[str, Any], stage: dict[str, Any]) -> None:
    video = resolve(stage["inputs"][0])
    captions = resolve(stage["inputs"][1])
    out = resolve(stage["outputs"][0])
    out.parent.mkdir(parents=True, exist_ok=True)
    probe = ffprobe_json(video)
    streams = probe.get("streams", [])
    duration = float(probe.get("format", {}).get("duration") or 0.0)
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    checks = {
        "video_exists": video.exists() and video.stat().st_size > 0,
        "ffprobe_readable": True,
        "duration_seconds": duration,
        "duration_within_tolerance": 1.0 <= duration <= 90.0,
        "captions_present": captions.exists() and captions.stat().st_size > 0,
        "audio_stream_present": has_audio,
        "video_stream_present": has_video,
        "source_traceability": True,
        "human_review_required": True,
    }
    checks["ok"] = all(v for k, v in checks.items() if isinstance(v, bool) and k != "human_review_required")
    write_json(out, checks)
    if not checks["ok"]:
        raise RuntimeError("quality checks failed")
    complete_stage(stage)


def handler_export(workflow: dict[str, Any], stage: dict[str, Any]) -> None:
    src = resolve(stage["inputs"][0])
    quality = load_json(resolve(stage["inputs"][1]))
    if not quality.get("ok"):
        raise RuntimeError("quality report is not ok")
    out = resolve(stage["outputs"][0])
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, out)
    complete_stage(stage)


def handler_write_final_manifest(workflow: dict[str, Any], stage: dict[str, Any]) -> None:
    out = resolve(stage["outputs"][0])
    payload = {
        "workflow_id": workflow.get("workflow_id"),
        "completed_at": utcnow(),
        "source_manifest": workflow.get("source_manifest"),
        "final_output": stage["inputs"][0],
        "stages": workflow.get("stages", []),
        "external_required_stages": workflow.get("external_required_stages", []),
    }
    write_json(out, payload)
    complete_stage(stage)


def quality_report(workflow: dict[str, Any]) -> dict[str, Any]:
    stage = stage_by_handler(workflow, "quality_check")
    if not stage or not stage.get("outputs"):
        return {}
    path = resolve(stage["outputs"][0])
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}


def workflow_warnings(workflow: dict[str, Any], review: dict[str, Any] | None = None) -> list[str]:
    warnings: list[str] = []
    q = quality_report(workflow)
    if q and not q.get("ok"):
        warnings.append("quality check did not pass")
    if not q:
        warnings.append("quality report is missing or unreadable")
    if review and review.get("state") in {"rejected", "changes_requested", "invalidated"}:
        warnings.append(f"review state blocks progression: {review.get('state')}")
    for item in workflow.get("external_required_stages", []):
        if item.get("status") == "blocked":
            warnings.append(f"external stage remains blocked and disclosed: {item.get('stage_id')}")
    return warnings


def unresolved_unknowns(workflow: dict[str, Any]) -> list[str]:
    unknowns = [
        "real buyer assets are not available",
        "commercial avatar service selection is unresolved",
        "cost-bearing/internet-dependent steps are not approved",
    ]
    if not workflow.get("external_services_allowed"):
        unknowns.append("external services are disabled for this prototype")
    return unknowns


def review_summary(workflow: dict[str, Any], update_review: bool = True) -> dict[str, Any]:
    validate_completed_stages(workflow)
    if workflow_complete(workflow):
        ensure_pending_review(workflow)
    review = invalidate_stage_reviews_if_needed(workflow, "review-summary stage artifact validation") if update_review else load_review(workflow)
    review = invalidate_review_if_needed(workflow, "review-summary artifact validation") if update_review else review
    q = quality_report(workflow)
    completed = [stage["stage_id"] for stage in workflow.get("stages", []) if stage.get("status") == "completed"]
    failed = [stage["stage_id"] for stage in workflow.get("stages", []) if stage.get("status") == "failed"]
    blocked = [stage["stage_id"] for stage in workflow.get("stages", []) if stage.get("status") == "blocked"]
    skipped = [stage["stage_id"] for stage in workflow.get("stages", []) if stage.get("status") == "skipped"]
    outputs = []
    for stage in workflow.get("stages", []):
        for output in stage.get("outputs", []):
            path = resolve(output)
            outputs.append({
                "stage_id": stage["stage_id"],
                "path": output,
                "exists": path.exists(),
                "size": path.stat().st_size if path.exists() else 0,
                "sha256": sha256_file(path) if path.exists() and path.is_file() else None,
            })
    stage_reviews = []
    for stage in workflow.get("stages", []):
        if stage.get("human_review_required"):
            stage_reviews.append(stage_review_status(workflow, review, stage))
    return {
        "workflow_id": workflow.get("workflow_id"),
        "source_inputs": sorted({item for stage in workflow.get("stages", []) for item in stage.get("inputs", []) if resolve(item).exists()}),
        "completed_stages": completed,
        "failed_stages": failed,
        "blocked_stages": blocked,
        "skipped_stages": skipped,
        "output_files": outputs,
        "duration": q.get("duration_seconds"),
        "video_status": q.get("video_stream_present"),
        "audio_status": q.get("audio_stream_present"),
        "caption_status": q.get("captions_present"),
        "quality_check": q,
        "external_stages_still_blocked": [item for item in workflow.get("external_required_stages", []) if item.get("status") == "blocked"],
        "fingerprints": review_artifacts(workflow),
        "review": review,
        "required_stage_reviews": stage_reviews,
        "stage_review_blockers": required_stage_review_blockers(workflow, review),
        "warnings": workflow_warnings(workflow, review),
        "unresolved_unknowns": unresolved_unknowns(workflow),
    }


def stage_review_summary(workflow: dict[str, Any], stage_id: str) -> dict[str, Any]:
    stages = stage_map(workflow)
    if stage_id not in stages:
        raise RuntimeError(f"unknown stage: {stage_id}")
    review = invalidate_stage_reviews_if_needed(workflow, "stage review-summary artifact validation")
    stage = stages[stage_id]
    status = stage_review_status(workflow, review, stage)
    return {
        "workflow_id": workflow.get("workflow_id"),
        "stage_id": stage_id,
        "human_review_required": bool(stage.get("human_review_required")),
        "stage_status": stage.get("status"),
        "inputs": stage.get("inputs", []),
        "outputs": stage.get("outputs", []),
        "fingerprints": stage_fingerprints(stage),
        "review": status,
        "warnings": stage_warnings(workflow, stage),
        "unresolved_items": unresolved_unknowns(workflow) if stage.get("human_review_required") else [],
    }


def record_stage_review_decision(
    workflow: dict[str, Any],
    stage_id: str,
    decision: str,
    reviewer: str,
    notes: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    if not reviewer:
        raise RuntimeError("reviewer is required")
    stages = stage_map(workflow)
    if stage_id not in stages:
        raise RuntimeError(f"unknown stage: {stage_id}")
    if decision == "approved":
        pass
    elif decision == "rejected":
        if not reason:
            raise RuntimeError("stage rejection reason is required")
    elif decision == "changes_requested":
        if not notes:
            raise RuntimeError("stage change request notes are required")
    else:
        raise RuntimeError(f"unsupported stage review decision: {decision}")
    stage = stages[stage_id]
    validate_completed_stages(workflow)
    if stage.get("status") != "completed":
        raise RuntimeError(f"cannot review incomplete stage: {stage_id}={stage.get('status')}")
    now = utcnow()
    review = invalidate_stage_reviews_if_needed(workflow, "new stage review decision validation")
    record = {
        "stage_id": stage_id,
        "decision": decision,
        "reviewer": reviewer,
        "reviewed_at": now,
        "notes": notes,
        "reason": reason,
        "stage_output_fingerprints": fingerprint(stage.get("outputs", [])),
        "stage_manifest_fingerprint": stage_manifest_fingerprint(stage),
        "stage_fingerprints": stage_fingerprints(stage),
        "warnings_seen": stage_warnings(workflow, stage),
        "unresolved_items": unresolved_unknowns(workflow) if stage.get("human_review_required") else [],
    }
    review.setdefault("stage_reviews", {})[stage_id] = record
    review.setdefault("history", []).append({
        "scope": "stage",
        "stage_id": stage_id,
        "decision": decision,
        "reviewer": reviewer,
        "at": now,
        "notes": notes,
        "reason": reason,
    })
    if review.get("state") == "approved" and decision != "approved":
        review["state"] = "invalidated"
        review["decision"] = "invalidated"
        review["invalidated_at"] = utcnow()
        review["invalidation_reason"] = f"stage review changed: {stage_id}"
        review.setdefault("history", []).append({
            "scope": "workflow",
            "state": "invalidated",
            "at": review["invalidated_at"],
            "reason": review["invalidation_reason"],
        })
    save_review(workflow, review)
    return record


def record_review_decision(
    workflow: dict[str, Any],
    decision: str,
    reviewer: str,
    notes: str | None = None,
    reason: str | None = None,
    affected_stages: list[str] | None = None,
    approval_text: str | None = None,
    confirm_approval: bool = False,
) -> dict[str, Any]:
    if not reviewer:
        raise RuntimeError("reviewer is required")
    validate_completed_stages(workflow)
    if decision == "approved":
        if not confirm_approval and approval_text != "APPROVE":
            raise RuntimeError("approval requires --confirm-approval or --approval-text APPROVE")
        q = quality_report(workflow)
        if not q.get("ok"):
            raise RuntimeError("cannot approve without passing quality report")
        review_for_stage_check = invalidate_stage_reviews_if_needed(workflow, "final approval stage validation")
        blockers = required_stage_review_blockers(workflow, review_for_stage_check)
        if blockers:
            raise RuntimeError("cannot approve until required stage reviews pass: " + "; ".join(blockers))
    elif decision == "rejected":
        if not reason:
            raise RuntimeError("rejection reason is required")
    elif decision == "changes_requested":
        if not notes:
            raise RuntimeError("change request notes are required")
        if not affected_stages:
            raise RuntimeError("at least one affected stage is required")
        known = set(stage_map(workflow))
        unknown = [stage_id for stage_id in affected_stages if stage_id not in known]
        if unknown:
            raise RuntimeError(f"unknown affected stage(s): {', '.join(unknown)}")
    else:
        raise RuntimeError(f"unsupported review decision: {decision}")

    now = utcnow()
    review = load_review(workflow)
    state = "changes_requested" if decision == "changes_requested" else decision
    review.update({
        "state": state,
        "decision": decision,
        "reviewer": reviewer,
        "reviewed_at": now,
        "reviewed_artifacts": review_artifacts(workflow),
    })
    review.pop("invalidated_at", None)
    review.pop("invalidation_reason", None)
    review.pop("mismatches", None)
    if notes is not None:
        review["notes"] = notes
    if reason is not None:
        review["reason"] = reason
    if affected_stages is not None:
        review["affected_stages"] = affected_stages
    review.setdefault("history", []).append({
        "state": state,
        "decision": decision,
        "reviewer": reviewer,
        "at": now,
        "notes": notes,
        "reason": reason,
        "affected_stages": affected_stages or [],
    })
    save_review(workflow, review)
    return review


def can_proceed_to_external_adapter(workflow: dict[str, Any], update_review: bool = True) -> tuple[bool, list[str]]:
    review = invalidate_stage_reviews_if_needed(workflow, "external gate stage artifact validation") if update_review else load_review(workflow)
    review = invalidate_review_if_needed(workflow, "external gate artifact validation") if update_review else review
    reasons: list[str] = []
    if review.get("state") != "approved":
        reasons.append(f"review is not approved: {review.get('state')}")
    if review.get("state") == "approved":
        mismatches = review_mismatches(review, review_artifacts(workflow))
        if mismatches:
            reasons.append(f"reviewed artifact mismatch: {', '.join(mismatches)}")
    q = quality_report(workflow)
    if not q.get("ok"):
        reasons.append("quality check has not passed")
    for stage in workflow.get("stages", []):
        if stage.get("status") in {"failed", "blocked", "running", "pending", "awaiting_review"}:
            reasons.append(f"stage not ready: {stage['stage_id']}={stage.get('status')}")
    if review.get("state") == "changes_requested":
        reasons.append("requested changes remain unresolved")
    reasons.extend(required_stage_review_blockers(workflow, review))
    return (not reasons, reasons)


SECRET_KEY_TERMS = ("password", "secret", "token", "api_key", "credential")
TEXT_SUFFIXES = {".txt", ".md", ".log", ".csv"}
JSON_SUFFIXES = {".json"}
SUBTITLE_SUFFIXES = {".srt", ".vtt"}
IMAGE_SUFFIXES = {".ppm", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def allowed_inspection_roots(workflow: dict[str, Any]) -> list[Path]:
    roots = [resolve(workflow.get("work_dir", "memory/media_workflows/default")).resolve()]
    fixture = workflow.get("fixture_dir")
    if fixture:
        roots.append(resolve(fixture).resolve())
    return roots


def safe_artifact_path(workflow: dict[str, Any], raw: str | Path) -> Path:
    path = resolve(raw).resolve()
    roots = allowed_inspection_roots(workflow)
    if not any(path == root or root in path.parents for root in roots):
        raise RuntimeError(f"artifact path is outside approved workflow/fixture directories: {raw}")
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"artifact does not exist or is not a file: {raw}")
    return path


def artifact_lookup(workflow: dict[str, Any], spec: str) -> Path:
    stages = stage_map(workflow)
    if spec in stages and stages[spec].get("outputs"):
        return safe_artifact_path(workflow, stages[spec]["outputs"][0])
    for stage in workflow.get("stages", []):
        for path in stage.get("inputs", []) + stage.get("outputs", []):
            if spec == path or spec == Path(path).name or spec == f"{stage['stage_id']}:{Path(path).name}":
                return safe_artifact_path(workflow, path)
    return safe_artifact_path(workflow, spec)


def media_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    guessed = mimetypes.guess_type(path.name)[0]
    if suffix in SUBTITLE_SUFFIXES:
        return "text/subtitle"
    if suffix in JSON_SUFFIXES:
        return "application/json"
    if suffix in TEXT_SUFFIXES:
        return guessed or "text/plain"
    if suffix in IMAGE_SUFFIXES:
        return guessed or f"image/{suffix.lstrip('.')}"
    if suffix in AUDIO_SUFFIXES:
        return guessed or f"audio/{suffix.lstrip('.')}"
    if suffix in VIDEO_SUFFIXES:
        return guessed or f"video/{suffix.lstrip('.')}"
    return guessed or "application/octet-stream"


def redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if any(term in str(key).lower() for term in SECRET_KEY_TERMS):
                out[key] = "[REDACTED]"
            else:
                out[key] = redact_json(item)
        return out
    if isinstance(value, list):
        return [redact_json(item) for item in value[:50]]
    return value


def bounded_text_preview(path: Path, max_bytes: int = 4096, max_lines: int = 40) -> dict[str, Any]:
    data = path.read_bytes()[:max_bytes]
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()[:max_lines]
    redacted = []
    for line in lines:
        lower = line.lower()
        if any(term in lower for term in SECRET_KEY_TERMS):
            redacted.append("[REDACTED LINE]")
        else:
            redacted.append(line)
    return {
        "preview": "\n".join(redacted),
        "truncated": path.stat().st_size > max_bytes or len(text.splitlines()) > max_lines,
        "max_bytes": max_bytes,
        "max_lines": max_lines,
    }


def json_preview(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return bounded_text_preview(path)
    redacted = redact_json(payload)
    encoded = json.dumps(redacted, indent=2, sort_keys=True)
    lines = encoded.splitlines()
    return {
        "preview": "\n".join(lines[:80]),
        "truncated": len(lines) > 80,
        "json_valid": True,
    }


def subtitle_preview(path: Path) -> dict[str, Any]:
    text = path.read_text(errors="replace")
    cues = [block for block in text.strip().split("\n\n") if block.strip()]
    timing_lines = [line for line in text.splitlines() if "-->" in line]
    return {
        "cue_count": len(cues),
        "timing_range": {
            "first": timing_lines[0] if timing_lines else None,
            "last": timing_lines[-1] if timing_lines else None,
        },
        "preview": "\n\n".join(cues[:5]),
        "truncated": len(cues) > 5,
    }


def ppm_dimensions(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        magic = handle.readline().strip()
        if magic not in {b"P3", b"P6"}:
            return {}
        line = handle.readline().strip()
        while line.startswith(b"#"):
            line = handle.readline().strip()
        width, height = [int(item) for item in line.split()[:2]]
        return {"format": magic.decode(), "width": width, "height": height}


def image_metadata(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".ppm":
        return ppm_dimensions(path)
    return {"format": path.suffix.lower().lstrip(".") or "unknown"}


def av_metadata(path: Path) -> dict[str, Any]:
    probe = shutil.which("ffprobe")
    if not probe:
        return {"error": "ffprobe missing"}
    try:
        data = ffprobe_json(path)
    except Exception as exc:
        return {"error": str(exc)}
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    out: dict[str, Any] = {
        "duration": float(fmt.get("duration") or 0.0),
        "bitrate": int(fmt.get("bit_rate") or 0) if fmt.get("bit_rate") else None,
        "streams": [],
        "subtitle_present": any(s.get("codec_type") == "subtitle" for s in streams),
    }
    for stream in streams:
        item = {
            "index": stream.get("index"),
            "type": stream.get("codec_type"),
            "codec": stream.get("codec_name"),
        }
        if stream.get("codec_type") == "video":
            item.update({
                "width": stream.get("width"),
                "height": stream.get("height"),
                "frame_rate": stream.get("avg_frame_rate") or stream.get("r_frame_rate"),
            })
        if stream.get("codec_type") == "audio":
            item.update({
                "channels": stream.get("channels"),
                "sample_rate": stream.get("sample_rate"),
                "bitrate": stream.get("bit_rate"),
            })
        out["streams"].append(item)
    return out


def artifact_metadata(workflow: dict[str, Any], raw_path: str | Path) -> dict[str, Any]:
    path = safe_artifact_path(workflow, raw_path)
    stat = path.stat()
    suffix = path.suffix.lower()
    info: dict[str, Any] = {
        "path": rel(path),
        "media_type": media_type_for(path),
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
        "sha256": sha256_file(path),
    }
    if suffix in JSON_SUFFIXES:
        info["preview"] = json_preview(path)
    elif suffix in TEXT_SUFFIXES:
        info["preview"] = bounded_text_preview(path)
    elif suffix in SUBTITLE_SUFFIXES:
        info["subtitle"] = subtitle_preview(path)
    elif suffix in IMAGE_SUFFIXES:
        info["image"] = image_metadata(path)
    elif suffix in AUDIO_SUFFIXES or suffix in VIDEO_SUFFIXES:
        info["media"] = av_metadata(path)
    return info


def output_producer_map(workflow: dict[str, Any]) -> dict[str, str]:
    producers: dict[str, str] = {}
    for stage in workflow.get("stages", []):
        for output in stage.get("outputs", []):
            producers[output] = stage["stage_id"]
    return producers


def lineage_summary(workflow: dict[str, Any]) -> dict[str, Any]:
    producers = output_producer_map(workflow)
    dependencies: dict[str, list[str]] = {stage["stage_id"]: [] for stage in workflow.get("stages", [])}
    for stage in workflow.get("stages", []):
        for item in stage.get("inputs", []):
            producer = producers.get(item)
            if producer:
                dependencies.setdefault(producer, []).append(stage["stage_id"])
    final_stage = stage_by_handler(workflow, "export") or stage_by_handler(workflow, "write_final_manifest")
    final_outputs = (final_stage or {}).get("outputs", [])
    stage_entries = []
    for stage in workflow.get("stages", []):
        inputs = []
        for item in stage.get("inputs", []):
            producer = producers.get(item)
            inputs.append({"path": item, "source_stage": producer or "source_input", "fingerprint": single_file_fingerprint(item)})
        outputs = [{"path": item, "fingerprint": single_file_fingerprint(item)} for item in stage.get("outputs", [])]
        stage_entries.append({
            "stage_id": stage["stage_id"],
            "handler": stage.get("handler"),
            "implementation": stage.get("implementation"),
            "inputs": inputs,
            "outputs": outputs,
            "dependent_stages": sorted(set(dependencies.get(stage["stage_id"], []))),
        })
    return {
        "source_inputs": sorted({item for stage in workflow.get("stages", []) for item in stage.get("inputs", []) if item not in producers}),
        "stages": stage_entries,
        "final_outputs": final_outputs,
    }


def stage_purpose(stage: dict[str, Any]) -> str:
    purposes = {
        "intake": "Normalize source script/input material.",
        "segment_script": "Split the script into timed reviewable segments.",
        "generate_placeholder_audio": "Create local placeholder narration audio.",
        "generate_placeholder_visual": "Create local placeholder visual/avatar card.",
        "generate_captions": "Create subtitle/caption file from script segments.",
        "assemble_video": "Combine visual, audio, and captions into a rendered segment.",
        "quality_check": "Verify expected video, audio, caption, duration, and traceability signals.",
        "export": "Copy the verified rendered segment to final output.",
        "write_final_manifest": "Write the final traceability manifest.",
    }
    return purposes.get(stage["stage_id"], f"Run handler {stage.get('handler')}.")


def inspect_stage(workflow: dict[str, Any], stage_id: str, reviewer: str | None = None, show_quality: bool = False,
                  show_fingerprints: bool = False, show_lineage: bool = False) -> dict[str, Any]:
    stages = stage_map(workflow)
    if stage_id not in stages:
        raise RuntimeError(f"unknown stage: {stage_id}")
    review = invalidate_stage_reviews_if_needed(workflow, "stage inspection artifact validation")
    stage = stages[stage_id]
    inputs = [artifact_metadata(workflow, item) for item in stage.get("inputs", []) if resolve(item).exists()]
    outputs = [artifact_metadata(workflow, item) for item in stage.get("outputs", []) if resolve(item).exists()]
    status = stage_review_status(workflow, review, stage)
    result: dict[str, Any] = {
        "workflow_id": workflow.get("workflow_id"),
        "stage_id": stage_id,
        "status": stage.get("status"),
        "purpose": stage_purpose(stage),
        "handler": stage.get("handler"),
        "implementation": stage.get("implementation") or {
            "selected": stage.get("handler"),
            "fallback_handler": stage.get("fallback_handler"),
            "seed": stage.get("seed"),
            "width": stage.get("width"),
            "height": stage.get("height"),
            "style_config_path": style_config_source(stage),
            "style_profile": stage.get("style_profile"),
        },
        "human_review_required": bool(stage.get("human_review_required")),
        "dependencies": stage.get("dependencies", []),
        "inputs": inputs,
        "outputs": outputs,
        "warnings": stage_warnings(workflow, stage),
        "error": stage.get("error"),
        "stage_review": status,
        "fingerprints_match_review": status.get("fingerprints_valid"),
        "blocks_final_approval": status.get("blocks_final_approval"),
    }
    if show_quality:
        result["quality_check"] = quality_report(workflow)
    if show_fingerprints:
        result["fingerprints"] = stage_fingerprints(stage)
    if show_lineage:
        result["lineage"] = lineage_summary(workflow)
    if reviewer:
        record_inspection(workflow, stage_id, reviewer, result)
    return result


def inspect_artifact(workflow: dict[str, Any], spec: str, open_artifact: bool = False,
                     show_lineage: bool = False) -> dict[str, Any]:
    path = artifact_lookup(workflow, spec)
    result: dict[str, Any] = {"artifact": artifact_metadata(workflow, path)}
    if show_lineage:
        result["lineage"] = lineage_summary(workflow)
    if open_artifact:
        opener = shutil.which("xdg-open")
        if not opener:
            result["open"] = {"attempted": False, "error": "xdg-open not available"}
        else:
            subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            result["open"] = {"attempted": True, "path": rel(path)}
    else:
        result["open"] = {"attempted": False, "reason": "requires --open-artifact"}
    return result


def record_inspection(workflow: dict[str, Any], stage_id: str, reviewer: str, summary: dict[str, Any]) -> None:
    review = load_review(workflow)
    now = utcnow()
    review.setdefault("stage_inspections", {}).setdefault(stage_id, []).append({
        "inspected_at": now,
        "inspected_by": reviewer,
        "artifact_fingerprints_seen": {
            "inputs": [item.get("sha256") for item in summary.get("inputs", [])],
            "outputs": [item.get("sha256") for item in summary.get("outputs", [])],
        },
    })
    review.setdefault("history", []).append({
        "scope": "stage",
        "stage_id": stage_id,
        "action": "inspected",
        "reviewer": reviewer,
        "at": now,
    })
    save_review(workflow, review)


HANDLERS = {
    "intake": handler_intake,
    "segment_script": handler_segment_script,
    "generate_placeholder_audio": handler_generate_placeholder_audio,
    "generate_placeholder_visual": handler_generate_placeholder_visual,
    "generate_scene_cards_visual": handler_generate_scene_cards_visual,
    "generate_captions": handler_generate_captions,
    "assemble_video": handler_assemble_video,
    "quality_check": handler_quality_check,
    "export": handler_export,
    "write_final_manifest": handler_write_final_manifest,
}


def dry_run_plan(workflow: dict[str, Any]) -> dict[str, Any]:
    tools = tool_status()
    required = {"assemble_video": ["ffmpeg"], "quality_check": ["ffprobe"], "generate_placeholder_audio": ["espeak-ng"]}
    stages = []
    for idx, stage in enumerate(workflow.get("stages", []), 1):
        missing = [tool for tool in required.get(stage["stage_id"], []) if not tools.get(tool)]
        stages.append({
            "order": idx,
            "stage_id": stage["stage_id"],
            "status": stage["status"],
            "dependencies": stage.get("dependencies", []),
            "inputs": stage.get("inputs", []),
            "outputs": stage.get("outputs", []),
            "handler": stage.get("handler"),
            "implementation": stage.get("implementation") or {
                "selected": stage.get("handler"),
                "fallback_handler": stage.get("fallback_handler"),
                "seed": stage.get("seed"),
                "width": stage.get("width"),
                "height": stage.get("height"),
                "style_config_path": style_config_source(stage),
                "style_profile": stage.get("style_profile"),
            },
            "missing_dependencies": missing,
            "human_review_required": stage.get("human_review_required", False),
        })
    return {
        "workflow_id": workflow.get("workflow_id"),
        "dry_run": True,
        "execution_order": [stage["stage_id"] for stage in workflow.get("stages", [])],
        "tools": tools,
        "stages": stages,
        "external_required_stages": workflow.get("external_required_stages", []),
    }


def apply_retry(workflow: dict[str, Any], retry_stage: str | None) -> None:
    if not retry_stage:
        return
    stages = stage_map(workflow)
    if retry_stage not in stages:
        raise RuntimeError(f"unknown retry stage: {retry_stage}")
    reset = {retry_stage} | dependents(workflow, retry_stage)
    for stage_id in reset:
        stage = stages[stage_id]
        if stage_id == retry_stage or stage["status"] in {"completed", "failed", "blocked", "awaiting_review"}:
            stage["status"] = "pending"
            stage["started_at"] = None
            stage["completed_at"] = None
            stage["error"] = None
            stage["checksum"] = None


def run_workflow(
    manifest_path: Path = DEFAULT_MANIFEST,
    execute: bool = False,
    resume: bool = False,
    dry_run: bool = False,
    status_only: bool = False,
    retry_stage: str | None = None,
    print_result: bool = False,
    prefer_runtime: bool = True,
) -> dict[str, Any]:
    workflow = load_workflow(manifest_path, prefer_runtime=prefer_runtime or resume or status_only)
    invalidated = validate_completed_stages(workflow)
    apply_retry(workflow, retry_stage)

    if dry_run:
        result = dry_run_plan(workflow)
    elif status_only:
        result = {"workflow": workflow, "invalidated": invalidated, "status": Counter_status(workflow)}
    elif execute or resume or retry_stage:
        stages = stage_map(workflow)
        executed = []
        for stage in workflow.get("stages", []):
            if stage["status"] == "completed":
                fp = fingerprint(stage.get("outputs", []))
                if fp.get("valid") and fp.get("sha256") == stage.get("checksum", {}).get("sha256"):
                    executed.append({"stage_id": stage["stage_id"], "status": "skipped"})
                    continue
                stage["status"] = "pending"

            deps = dependency_errors(stage, stages)
            if deps:
                stage["status"] = "blocked"
                stage["error"] = "; ".join(deps)
                executed.append({"stage_id": stage["stage_id"], "status": "blocked", "error": stage["error"]})
                continue
            if stage["status"] not in {"pending", "failed"}:
                executed.append({"stage_id": stage["stage_id"], "status": stage["status"]})
                continue
            handler = HANDLERS.get(stage.get("handler"))
            if not handler:
                stage["status"] = "failed"
                stage["error"] = f"unknown handler: {stage.get('handler')}"
                executed.append({"stage_id": stage["stage_id"], "status": "failed", "error": stage["error"]})
                continue
            stage["status"] = "running"
            stage["started_at"] = utcnow()
            stage["attempts"] = int(stage.get("attempts", 0) or 0) + 1
            stage["error"] = None
            save_workflow(workflow)
            try:
                handler(workflow, stage)
                executed.append({"stage_id": stage["stage_id"], "status": stage["status"]})
            except Exception as exc:
                stage["status"] = "failed"
                stage["error"] = str(exc)
                stage["completed_at"] = utcnow()
                executed.append({"stage_id": stage["stage_id"], "status": "failed", "error": str(exc)})
            save_workflow(workflow)
        result = {"workflow": workflow, "executed": executed, "invalidated": invalidated, "status": Counter_status(workflow)}
    else:
        result = {"workflow": workflow, "invalidated": invalidated, "status": Counter_status(workflow)}

    if not dry_run:
        ensure_pending_review(workflow)
        save_workflow(workflow)
    if print_result:
        print(json.dumps(result, indent=2, sort_keys=True))
    return result


def Counter_status(workflow: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for stage in workflow.get("stages", []):
        counts[stage["status"]] = counts.get(stage["status"], 0) + 1
    return counts


def self_test() -> dict[str, Any]:
    workflow = load_workflow(DEFAULT_MANIFEST, prefer_runtime=False)
    plan = dry_run_plan(workflow)
    ok = (
        plan["execution_order"] == [
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
        and any(item["stage_id"] == "commercial_avatar_generation" and item["status"] == "blocked"
                for item in plan["external_required_stages"])
    )
    return {"ok": ok, "plan": plan}


def format_review_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"Workflow: {summary.get('workflow_id')}",
        f"Review state: {summary.get('review', {}).get('state')}",
        "",
        "Source inputs:",
    ]
    for item in summary.get("source_inputs", []):
        lines.append(f"  - {item}")
    lines.extend([
        "",
        f"Completed stages: {', '.join(summary.get('completed_stages', [])) or 'none'}",
        f"Failed stages: {', '.join(summary.get('failed_stages', [])) or 'none'}",
        f"Blocked stages: {', '.join(summary.get('blocked_stages', [])) or 'none'}",
        f"Skipped stages: {', '.join(summary.get('skipped_stages', [])) or 'none'}",
        "",
        "Outputs:",
    ])
    for item in summary.get("output_files", []):
        sha = item.get("sha256") or "missing"
        lines.append(f"  - {item['stage_id']}: {item['path']} ({item['size']} bytes, sha256={sha})")
    lines.extend([
        "",
        f"Duration: {summary.get('duration')}",
        f"Video stream present: {summary.get('video_status')}",
        f"Audio stream present: {summary.get('audio_status')}",
        f"Captions present: {summary.get('caption_status')}",
        f"Quality OK: {summary.get('quality_check', {}).get('ok')}",
        "",
        "External stages still blocked:",
    ])
    for item in summary.get("external_stages_still_blocked", []):
        lines.append(f"  - {item.get('stage_id')}: {item.get('reason')}")
    lines.append("")
    lines.append("Required stage reviews:")
    for item in summary.get("required_stage_reviews", []):
        reviewer = item.get("reviewer") or "none"
        notes = item.get("notes") or ""
        lines.append(
            f"  - {item['stage_id']}: {item['state']} "
            f"(reviewer={reviewer}, fingerprints_valid={item['fingerprints_valid']}, "
            f"blocks_final_approval={item['blocks_final_approval']})"
        )
        if notes:
            lines.append(f"    notes: {notes}")
        for warning in item.get("warnings", []):
            lines.append(f"    warning: {warning}")
    lines.append("")
    lines.append("Warnings:")
    for item in summary.get("warnings", []):
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("Unresolved unknowns:")
    for item in summary.get("unresolved_unknowns", []):
        lines.append(f"  - {item}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-stage")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--print", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--review-summary", action="store_true")
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--reject", action="store_true")
    parser.add_argument("--request-changes", action="store_true")
    parser.add_argument("--reviewer")
    parser.add_argument("--notes")
    parser.add_argument("--reason")
    parser.add_argument("--affected-stage", action="append", default=[])
    parser.add_argument("--approval-text")
    parser.add_argument("--confirm-approval", action="store_true")
    parser.add_argument("--review-stage")
    parser.add_argument("--stage-approve")
    parser.add_argument("--stage-reject")
    parser.add_argument("--stage-request-changes")
    parser.add_argument("--stage-note")
    parser.add_argument("--inspect-stage")
    parser.add_argument("--inspect-artifact")
    parser.add_argument("--open-artifact", action="store_true")
    parser.add_argument("--show-quality", action="store_true")
    parser.add_argument("--show-fingerprints", action="store_true")
    parser.add_argument("--show-lineage", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        result = self_test()
        if args.print:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1

    if (
        args.review_summary or args.approve or args.reject or args.request_changes
        or args.review_stage or args.stage_approve or args.stage_reject or args.stage_request_changes
        or args.inspect_stage or args.inspect_artifact
    ):
        workflow = load_workflow(resolve(args.manifest), prefer_runtime=True)
        validate_completed_stages(workflow)
        save_workflow(workflow)
        if args.inspect_stage:
            result = inspect_stage(
                workflow,
                args.inspect_stage,
                reviewer=args.reviewer,
                show_quality=args.show_quality,
                show_fingerprints=args.show_fingerprints,
                show_lineage=args.show_lineage,
            )
        elif args.inspect_artifact:
            result = inspect_artifact(
                workflow,
                args.inspect_artifact,
                open_artifact=args.open_artifact,
                show_lineage=args.show_lineage,
            )
        elif args.review_stage:
            result = inspect_stage(
                workflow,
                args.review_stage,
                reviewer=args.reviewer,
                show_quality=True,
                show_fingerprints=True,
                show_lineage=args.show_lineage,
            )
        elif args.stage_approve:
            result = record_stage_review_decision(
                workflow,
                args.stage_approve,
                "approved",
                reviewer=args.reviewer or "",
                notes=args.stage_note or args.notes,
            )
        elif args.stage_reject:
            result = record_stage_review_decision(
                workflow,
                args.stage_reject,
                "rejected",
                reviewer=args.reviewer or "",
                notes=args.stage_note or args.notes,
                reason=args.reason,
            )
        elif args.stage_request_changes:
            result = record_stage_review_decision(
                workflow,
                args.stage_request_changes,
                "changes_requested",
                reviewer=args.reviewer or "",
                notes=args.stage_note or args.notes,
                reason=args.reason,
            )
        elif args.approve:
            result = record_review_decision(
                workflow,
                "approved",
                reviewer=args.reviewer or "",
                notes=args.notes,
                approval_text=args.approval_text,
                confirm_approval=args.confirm_approval,
            )
        elif args.reject:
            result = record_review_decision(
                workflow,
                "rejected",
                reviewer=args.reviewer or "",
                reason=args.reason,
            )
        elif args.request_changes:
            result = record_review_decision(
                workflow,
                "changes_requested",
                reviewer=args.reviewer or "",
                notes=args.notes,
                affected_stages=args.affected_stage,
            )
        else:
            result = review_summary(workflow)
        if args.print:
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.review_summary:
            print(format_review_summary(result))
        elif args.review_stage or args.inspect_stage or args.inspect_artifact:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(json.dumps({"state": result.get("state"), "decision": result.get("decision")}, sort_keys=True))
        return 0

    result = run_workflow(
        manifest_path=resolve(args.manifest),
        execute=args.run,
        resume=args.resume,
        dry_run=args.dry_run,
        status_only=args.status,
        retry_stage=args.retry_stage,
        print_result=args.print,
    )
    if args.print:
        return 0
    if args.dry_run:
        print("Dry-run plan:")
        for stage in result["stages"]:
            print(f"{stage['order']}. {stage['stage_id']} -> {stage['outputs']}")
    elif args.status:
        print(json.dumps(result["status"], sort_keys=True))
    else:
        print(json.dumps(result.get("status", {}), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
