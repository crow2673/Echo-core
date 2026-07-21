#!/usr/bin/env python3
"""Tests for Outcome Loop evidence-only Executive Context integration."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core import executive_context, outcome_loop


CURRENT_CONTEXT = {
    "current_objective": "Build and verify the memory optimization script.",
    "current_focus": "Missing memory optimization script (tools/memory_optimization.py)",
    "active_task": {"task": "Create tools/memory_optimization.py"},
}


def _report(
    records: list[dict],
    updated_at: str = "2026-07-10T15:30:00+00:00",
    executive: dict | None = None,
) -> dict:
    frozen_now = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    if frozen_now.tzinfo is None:
        frozen_now = frozen_now.replace(tzinfo=timezone.utc)
    return outcome_loop.build_report(records, executive_context=executive, now=frozen_now) | {"updated_at": updated_at}


class OutcomeLoopExecutiveContextTests(unittest.TestCase):
    def test_verified_success_updates_evidence_fields(self) -> None:
        report = _report([
            {
                "action_id": "memory_optimization:script_created",
                "category": "self_improvement",
                "description": "Create memory optimization script",
                "status": "succeeded",
                "score": 1.0,
                "expected_result": "tools/memory_optimization.py exists",
                "evidence": "verified memory optimization script exists",
                "last_checked_at": "2026-07-10T15:29:00+00:00",
            }
        ], executive=CURRENT_CONTEXT)

        evidence = outcome_loop.build_executive_evidence(report, CURRENT_CONTEXT)

        self.assertEqual(evidence["objective_progress"], "verified_progress")
        self.assertEqual(evidence["last_verified_success"]["action_id"], "memory_optimization:script_created")
        self.assertIsNone(evidence["last_verified_failure"])
        self.assertIn("memory/outcome_loop_report.json", evidence["evidence_sources"])
        self.assertIn("executive_context.current_objective", evidence["evidence_sources"])

    def test_verified_failure_updates_evidence_fields(self) -> None:
        report = _report([
            {
                "action_id": "memory_optimization:script_created",
                "category": "self_improvement",
                "description": "Create memory optimization script",
                "status": "failed",
                "score": -1.0,
                "expected_result": "tools/memory_optimization.py exists",
                "evidence": "tools/memory_optimization.py missing or too small",
                "last_checked_at": "2026-07-10T15:29:00+00:00",
            }
        ], executive=CURRENT_CONTEXT)

        evidence = outcome_loop.build_executive_evidence(report, CURRENT_CONTEXT)

        self.assertEqual(evidence["objective_progress"], "blocked_or_regressed")
        self.assertEqual(evidence["last_verified_failure"]["action_id"], "memory_optimization:script_created")
        self.assertIsNone(evidence["last_verified_success"])

    def test_open_build_requests_are_pending_review_not_failure(self) -> None:
        report = _report([
            {
                "action_id": "self_improvement:growth_requests_closed",
                "category": "self_improvement",
                "description": "Reviewed build queue should not contain stale open requests after verified repair.",
                "verifier_type": "open_build_requests_max",
                "status": "failed",
                "score": -1.0,
                "expected_result": "memory/growth_build_requests.json has 0 open reviewed build requests.",
                "evidence": "open reviewed build requests=3 > 0",
                "last_checked_at": "2026-07-10T15:29:00+00:00",
            }
        ], executive=CURRENT_CONTEXT)

        record = report["records"][0]
        evidence = outcome_loop.build_executive_evidence(report, CURRENT_CONTEXT)

        self.assertIn(record["outcome_state"], {"in_progress", "pending_review"})
        self.assertNotEqual(record["outcome_state"], "verified_failure")
        self.assertNotEqual(evidence["objective_progress"], "blocked_or_regressed")

    def test_unrelated_fiverr_success_does_not_drive_current_progress(self) -> None:
        report = _report([
            {
                "action_id": "income:fiverr_prework_package",
                "category": "economic_agency",
                "description": "Fiverr income prework should produce a local service package without account activity.",
                "status": "succeeded",
                "score": 1.0,
                "expected_result": "Latest Fiverr prework report has at least 5 services and lead evidence.",
                "evidence": "fiverr prework services=5; leads=3719; no account activity",
                "last_checked_at": "2026-07-10T15:29:00+00:00",
            }
        ], executive=CURRENT_CONTEXT)

        evidence = outcome_loop.build_executive_evidence(report, CURRENT_CONTEXT)

        self.assertEqual(report["records"][0]["outcome_state"], "unrelated")
        self.assertEqual(evidence["objective_progress"], "unverified")
        self.assertIsNone(evidence["last_verified_success"])

    def test_incomplete_evidence_is_unverified(self) -> None:
        status, score, evidence = outcome_loop.evaluate_record({
            "verifier_type": "unsupported_test_verifier",
            "verifier_config": "{}",
        })

        self.assertEqual(status, "unknown")
        self.assertEqual(score, 0.0)
        self.assertIn("unsupported verifier", evidence)

        report = _report([
            {
                "action_id": "memory_optimization:script_created",
                "category": "self_improvement",
                "description": "Create memory optimization script",
                "status": "unknown",
                "score": 0.0,
                "expected_result": "tools/memory_optimization.py exists",
                "evidence": "",
                "last_checked_at": "2026-07-10T15:29:00+00:00",
            }
        ], executive=CURRENT_CONTEXT)

        self.assertEqual(report["records"][0]["outcome_state"], "unverified")

    def test_stale_evidence_cannot_override_newer_relevant_evidence(self) -> None:
        report = _report([
            {
                "action_id": "memory_optimization:old_success",
                "category": "self_improvement",
                "description": "Create memory optimization script",
                "status": "succeeded",
                "score": 1.0,
                "expected_result": "tools/memory_optimization.py exists",
                "evidence": "old memory optimization script evidence",
                "last_checked_at": "2026-07-01T15:29:00+00:00",
            },
            {
                "action_id": "memory_optimization:new_failure",
                "category": "self_improvement",
                "description": "Create memory optimization script",
                "status": "failed",
                "score": -1.0,
                "expected_result": "tools/memory_optimization.py exists",
                "evidence": "tools/memory_optimization.py missing or too small",
                "last_checked_at": "2026-07-10T15:29:00+00:00",
            },
        ], executive=CURRENT_CONTEXT)

        evidence = outcome_loop.build_executive_evidence(report, CURRENT_CONTEXT)

        self.assertEqual(report["records"][0]["outcome_state"], "stale")
        self.assertEqual(evidence["objective_progress"], "blocked_or_regressed")
        self.assertEqual(evidence["last_verified_failure"]["action_id"], "memory_optimization:new_failure")

    def test_objective_progress_uses_only_relevant_evidence(self) -> None:
        report = _report([
            {
                "action_id": "income:fiverr_prework_package",
                "category": "economic_agency",
                "description": "Fiverr income prework",
                "status": "failed",
                "score": -1.0,
                "expected_result": "Fiverr report exists",
                "evidence": "fiverr login failed",
                "last_checked_at": "2026-07-10T15:28:00+00:00",
            },
            {
                "action_id": "memory_optimization:script_created",
                "category": "self_improvement",
                "description": "Create memory optimization script",
                "status": "succeeded",
                "score": 1.0,
                "expected_result": "tools/memory_optimization.py exists",
                "evidence": "verified memory optimization script exists",
                "last_checked_at": "2026-07-10T15:29:00+00:00",
            },
        ], executive=CURRENT_CONTEXT)

        evidence = outcome_loop.build_executive_evidence(report, CURRENT_CONTEXT)

        self.assertEqual(report["records"][0]["outcome_state"], "unrelated")
        self.assertEqual(evidence["objective_progress"], "verified_progress")

    def test_repeated_identical_evidence_does_not_duplicate_history_noise(self) -> None:
        original_path = executive_context.CONTEXT_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            executive_context.CONTEXT_PATH = Path(tmpdir) / "executive_context.json"
            try:
                record1 = {
                    "action_id": "test:success",
                    "category": "test",
                    "status": "succeeded",
                    "score": 1.0,
                    "expected_result": "done",
                    "evidence": "same evidence",
                    "last_checked_at": "2026-07-10T15:30:00+00:00",
                }
                record2 = {**record1, "last_checked_at": "2026-07-10T15:31:00+00:00"}
                report1 = _report([record1], updated_at="2026-07-10T15:30:00+00:00")
                report2 = _report([record2], updated_at="2026-07-10T15:31:00+00:00")
                outcome_loop.sync_executive_context(report1, {}, dry_run=False)
                first = executive_context.load_context(create=False)
                first_history_len = len(first.get("history", []))
                outcome_loop.sync_executive_context(report2, {}, dry_run=False)
                second = executive_context.load_context(create=False)
            finally:
                executive_context.CONTEXT_PATH = original_path

        self.assertEqual(first_history_len, len(second.get("history", [])))
        self.assertEqual(second["last_outcome_checked_at"], "2026-07-10T15:31:00+00:00")

    def test_outcome_loop_cannot_overwrite_authoritative_fields(self) -> None:
        original_path = executive_context.CONTEXT_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            executive_context.CONTEXT_PATH = Path(tmpdir) / "executive_context.json"
            try:
                executive_context.safe_update(
                    {
                        "system_health": "OK",
                        "current_focus": "keep focus",
                        "current_objective": "keep objective",
                        "active_task": {"task": "keep task"},
                    },
                    source="homeostasis",
                    reason="test setup",
                )
                executive_context.safe_update(
                    {
                        "system_health": "critical",
                        "current_focus": "bad focus",
                        "current_objective": "bad objective",
                        "active_task": {"task": "bad task"},
                        "last_verified_success": {"action_id": "ok"},
                    },
                    source="outcome_loop",
                    reason="test forbidden writes",
                )
                context = executive_context.load_context(create=False)
            finally:
                executive_context.CONTEXT_PATH = original_path

        self.assertEqual(context["system_health"], "OK")
        self.assertEqual(context["current_focus"], "keep focus")
        self.assertEqual(context["current_objective"], "keep objective")
        self.assertEqual(context["active_task"], {"task": "keep task"})
        self.assertEqual(context["last_verified_success"], {"action_id": "ok"})

    def test_existing_outcome_verifier_behavior_still_works(self) -> None:
        status, score, evidence = outcome_loop.evaluate_record({
            "verifier_type": "json_path_max",
            "verifier_config": '{"path":"memory/log_anomaly_signal_report.json","json_path":"active_core_operational_count","max":1000}',
        })

        self.assertIn(status, {"succeeded", "failed", "unknown"})
        self.assertIsInstance(score, float)
        self.assertTrue(evidence)


if __name__ == "__main__":
    unittest.main()
