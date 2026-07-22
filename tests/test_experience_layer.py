#!/usr/bin/env python3
"""Tests for verified Outcome Loop lessons in the Experience layer."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import executive_context, experience_layer


CONTEXT = {
    "current_objective": "Build and verify memory optimization.",
    "active_task": {"task": "Create tools/memory_optimization.py"},
}


def _record(action_id: str, outcome_state: str, relevance_status: str = "relevant") -> dict:
    raw_status = "succeeded" if outcome_state == "verified_success" else "failed"
    return {
        "action_id": action_id,
        "category": "self_improvement",
        "status": raw_status,
        "score": 1.0 if raw_status == "succeeded" else -1.0,
        "outcome_state": outcome_state,
        "relevance_status": relevance_status,
        "relevance_score": 0.9,
        "related_objective": CONTEXT["current_objective"],
        "related_task": CONTEXT["active_task"],
        "expected_result": "tools/memory_optimization.py exists",
        "observed_result": "verified memory optimization result",
        "evidence": "verified memory optimization result",
        "verification_reason": "relevant verifier produced current evidence",
        "last_checked_at": "2026-07-10T18:00:00+00:00",
    }


def _report(records: list[dict]) -> dict:
    return {
        "updated_at": "2026-07-10T18:01:00+00:00",
        "executive_context": CONTEXT,
        "records": records,
    }


class ExperienceLayerTests(unittest.TestCase):
    def test_verified_success_becomes_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "experience_lessons.jsonl"
            result = experience_layer.promote_from_outcome_report(
                _report([_record("memory:success", "verified_success")]),
                CONTEXT,
                lessons_path=path,
            )
            lessons = experience_layer.load_lessons(path)

        self.assertEqual(result["promoted_count"], 1)
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["outcome_state"], "verified_success")
        self.assertEqual(lessons[0]["source"], "outcome_loop")
        self.assertIn("worked", lessons[0]["lesson"])

    def test_verified_failure_becomes_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "experience_lessons.jsonl"
            result = experience_layer.promote_from_outcome_report(
                _report([_record("memory:failure", "verified_failure")]),
                CONTEXT,
                lessons_path=path,
            )
            lessons = experience_layer.load_lessons(path)

        self.assertEqual(result["promoted_count"], 1)
        self.assertEqual(lessons[0]["outcome_state"], "verified_failure")
        self.assertIn("failed", lessons[0]["lesson"])
        self.assertEqual(lessons[0]["failure_mode"], "relevant verifier produced current evidence")

    def test_unrelated_and_pending_records_are_not_lessons(self) -> None:
        records = [
            _record("income:fiverr", "verified_success", relevance_status="unrelated"),
            _record("growth:open", "pending_review"),
            _record("memory:unknown", "unverified"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "experience_lessons.jsonl"
            result = experience_layer.promote_from_outcome_report(
                _report(records),
                CONTEXT,
                lessons_path=path,
            )
            lessons = experience_layer.load_lessons(path)

        self.assertEqual(result["promoted_count"], 0)
        self.assertEqual(lessons, [])

    def test_duplicate_verified_lesson_is_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "experience_lessons.jsonl"
            report = _report([_record("memory:success", "verified_success")])
            first = experience_layer.promote_from_outcome_report(report, CONTEXT, lessons_path=path)
            second = experience_layer.promote_from_outcome_report(report, CONTEXT, lessons_path=path)
            lessons = experience_layer.load_lessons(path)

        self.assertEqual(first["promoted_count"], 1)
        self.assertEqual(second["promoted_count"], 0)
        self.assertEqual(second["skipped"]["duplicate"], 1)
        self.assertEqual(len(lessons), 1)

    def test_experience_layer_does_not_change_executive_context(self) -> None:
        original_path = executive_context.CONTEXT_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            executive_context.CONTEXT_PATH = Path(tmpdir) / "executive_context.json"
            try:
                before = executive_context.load_context(create=True)
                experience_layer.promote_from_outcome_report(
                    _report([_record("memory:success", "verified_success")]),
                    CONTEXT,
                    dry_run=True,
                    lessons_path=Path(tmpdir) / "experience_lessons.jsonl",
                )
                after = executive_context.load_context(create=False)
            finally:
                executive_context.CONTEXT_PATH = original_path

        self.assertEqual(before, after)

    def test_self_test_is_dry_run(self) -> None:
        result = experience_layer.self_test()

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["promoted_count"], 1)


if __name__ == "__main__":
    unittest.main()
