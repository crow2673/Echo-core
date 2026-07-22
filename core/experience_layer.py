#!/usr/bin/env python3
"""Verified experience lessons derived from Outcome Loop evidence.

Experience is not raw memory. This module records compact lessons only after an
outcome has been semantically classified as verified success or verified failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
LESSONS_PATH = BASE / "memory" / "experience_lessons.jsonl"
REPORT_PATH = BASE / "memory" / "experience_layer_report.json"

VERIFIED_STATES = {"verified_success", "verified_failure"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True)
    except Exception:
        return str(value)


def _jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        if not path.exists():
            return records
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                records.append(item)
    except Exception:
        return records
    return records


def load_lessons(path: Path | None = None) -> list[dict[str, Any]]:
    return _jsonl_records(path or LESSONS_PATH)


def _lesson_id(record: dict[str, Any], executive_context: dict[str, Any] | None = None) -> str:
    payload = {
        "action_id": record.get("action_id"),
        "outcome_state": record.get("outcome_state"),
        "expected_result": record.get("expected_result"),
        "observed_result": record.get("observed_result") or record.get("evidence"),
        "related_objective": record.get("related_objective") or (executive_context or {}).get("current_objective"),
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _active_task(executive_context: dict[str, Any] | None) -> Any:
    if not executive_context:
        return None
    return executive_context.get("active_task")


def _lesson_text(record: dict[str, Any]) -> str:
    action_id = record.get("action_id") or "unknown action"
    expected = record.get("expected_result") or "an expected result"
    observed = record.get("observed_result") or record.get("evidence") or "no observed result"
    reason = record.get("verification_reason") or "verified by Outcome Loop"
    if record.get("outcome_state") == "verified_success":
        return f"When {action_id} is expected to produce {expected}, evidence of {observed} means this approach worked because {reason}."
    return f"When {action_id} is expected to produce {expected}, evidence of {observed} means this approach failed because {reason}."


def _reuse_trigger(record: dict[str, Any]) -> str:
    category = record.get("category") or "unknown"
    expected = record.get("expected_result") or ""
    if record.get("outcome_state") == "verified_success":
        return f"Reuse when a future {category} task has a similar expected result: {expected}"
    return f"Check before repeating a future {category} task with a similar expected result: {expected}"


def lesson_from_outcome(
    record: dict[str, Any],
    executive_context: dict[str, Any] | None = None,
    checked_at: str | None = None,
) -> dict[str, Any] | None:
    """Convert one verified semantic outcome into a reusable lesson."""
    if record.get("outcome_state") not in VERIFIED_STATES:
        return None
    if record.get("relevance_status") != "relevant":
        return None

    confidence = 0.5
    if isinstance(record.get("relevance_score"), (int, float)):
        confidence = max(0.0, min(1.0, float(record["relevance_score"])))
    if record.get("outcome_state") == "verified_success" and confidence < 0.7:
        confidence = 0.7

    lesson = {
        "id": _lesson_id(record, executive_context),
        "created_at": utcnow(),
        "source": "outcome_loop",
        "source_report": "memory/outcome_loop_report.json",
        "source_checked_at": checked_at or record.get("last_checked_at"),
        "outcome_state": record.get("outcome_state"),
        "situation": record.get("related_objective") or (executive_context or {}).get("current_objective"),
        "action_taken": record.get("action_id"),
        "expected_result": record.get("expected_result"),
        "result": record.get("observed_result") or record.get("evidence"),
        "success_reason": record.get("verification_reason") if record.get("outcome_state") == "verified_success" else None,
        "failure_mode": record.get("verification_reason") if record.get("outcome_state") == "verified_failure" else None,
        "lesson": _lesson_text(record),
        "confidence": round(confidence, 3),
        "related_asset": record.get("related_asset"),
        "related_module": record.get("category"),
        "related_task": record.get("related_task") or _active_task(executive_context),
        "reuse_trigger": _reuse_trigger(record),
        "evidence": {
            "raw_status": record.get("status"),
            "score": record.get("score"),
            "evidence": record.get("evidence"),
            "relevance_status": record.get("relevance_status"),
            "relevance_score": record.get("relevance_score"),
            "evidence_age": record.get("evidence_age"),
        },
    }
    return lesson


def _append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.touch(exist_ok=True)
        return
    with path.open("a") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.rename(path)


def promote_from_outcome_report(
    outcome_report: dict[str, Any],
    executive_context: dict[str, Any] | None = None,
    dry_run: bool = False,
    lessons_path: Path | None = None,
) -> dict[str, Any]:
    """Promote verified Outcome Loop records into deduplicated lessons."""
    lessons_path = lessons_path or LESSONS_PATH
    existing_ids = {item.get("id") for item in load_lessons(lessons_path)}
    candidates = []
    skipped = {"not_verified": 0, "duplicate": 0}

    for record in outcome_report.get("records", []):
        lesson = lesson_from_outcome(
            record,
            executive_context=executive_context or outcome_report.get("executive_context"),
            checked_at=outcome_report.get("updated_at"),
        )
        if lesson is None:
            skipped["not_verified"] += 1
            continue
        if lesson["id"] in existing_ids:
            skipped["duplicate"] += 1
            continue
        existing_ids.add(lesson["id"])
        candidates.append(lesson)

    if not dry_run:
        _append_jsonl(lessons_path, candidates)

    report = {
        "updated_at": utcnow(),
        "dry_run": dry_run,
        "source": "outcome_loop",
        "lessons_path": str(lessons_path.relative_to(BASE)) if lessons_path.is_relative_to(BASE) else str(lessons_path),
        "candidate_count": len(candidates) + skipped["duplicate"],
        "promoted_count": len(candidates),
        "skipped": skipped,
        "lesson_ids": [lesson["id"] for lesson in candidates],
    }
    if not dry_run:
        write_json(REPORT_PATH, report)
    return report


def self_test() -> dict[str, Any]:
    sample_context = {
        "current_objective": "Build and verify memory optimization.",
        "active_task": {"task": "Create tools/memory_optimization.py"},
    }
    sample_report = {
        "updated_at": "2026-07-10T18:00:00+00:00",
        "executive_context": sample_context,
        "records": [
            {
                "action_id": "memory_optimization:script_created",
                "category": "self_improvement",
                "status": "succeeded",
                "score": 1.0,
                "outcome_state": "verified_success",
                "relevance_status": "relevant",
                "relevance_score": 0.9,
                "related_objective": sample_context["current_objective"],
                "related_task": sample_context["active_task"],
                "expected_result": "tools/memory_optimization.py exists",
                "observed_result": "verified memory optimization script exists",
                "evidence": "verified memory optimization script exists",
                "verification_reason": "relevant verifier succeeded with current evidence",
                "last_checked_at": "2026-07-10T17:59:00+00:00",
            },
            {
                "action_id": "income:fiverr_prework_package",
                "category": "economic_agency",
                "status": "succeeded",
                "outcome_state": "unrelated",
                "relevance_status": "unrelated",
                "expected_result": "Fiverr package exists",
                "evidence": "fiverr package exists",
            },
        ],
    }
    return promote_from_outcome_report(sample_report, sample_context, dry_run=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-outcome-report", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        result = self_test()
    elif args.from_outcome_report:
        report = json.loads((BASE / "memory" / "outcome_loop_report.json").read_text())
        result = promote_from_outcome_report(report, report.get("executive_context"), dry_run=args.dry_run)
    else:
        parser.error("choose --self-test or --from-outcome-report")

    if args.print:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
