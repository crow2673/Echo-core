#!/usr/bin/env python3
"""Tests for Day 3 unattended validator completion semantics."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import day3_unattended_validation as day3


def _show(active: str = "active", main_pid: str = "123", restarts: int = 0) -> dict:
    return {
        "stdout": (
            f"ActiveState={active}\n"
            "SubState=running\n"
            f"MainPID={main_pid}\n"
            "Result=success\n"
            f"NRestarts={restarts}"
        )
    }


def sample(
    index: int = 0,
    system_health: str = "OK",
    homeostasis_status: str = "ok",
    life_kind: str = "work",
    life_title: str = "Normal work",
    life_reason: str = "normal priority",
    blockers: list[dict] | None = None,
    active_core_count: int = 0,
    findings: list[dict] | None = None,
) -> dict:
    blockers = blockers or []
    findings = findings or []
    return {
        "sample_index": index,
        "systemctl": {
            "failed_units": {"stdout": "UNIT LOAD ACTIVE SUB DESCRIPTION\n\n0 loaded units listed."},
            "key_units": {"echo-core.service": {"show": _show()}},
        },
        "processes": {"echo_core_daemon_processes": ["python echo_core_daemon.py"]},
        "executive_context": {
            "system_health": system_health,
            "history": [],
            "capability_blockers": blockers,
        },
        "homeostasis": {
            "status": homeostasis_status,
            "anomaly_summary": {"active_core_operational_count": active_core_count},
            "findings": findings,
            "capability_blockers": blockers,
        },
        "life_loop": {
            "current_priority": {
                "kind": life_kind,
                "title": life_title,
                "reason": life_reason,
            }
        },
        "pulse": {
            "pulse_worker": {"age_seconds": 100},
            "heartbeat_worker": {"age_seconds": 30},
            "authoritative_writers": {
                "pulse": ["core.pulse", "echo-pulse.service"],
                "heartbeat": ["tools.heartbeat", "echo-heartbeat.service"],
            },
        },
        "outcome_loop": {"executive_evidence": {"outcome_evidence_signature": "same"}},
        "experience_layer": {"promoted_count": 0},
        "experience_lessons_tail": [],
        "temp_artifacts": [],
        "errors": [],
    }


class Day3ValidationTests(unittest.TestCase):
    def test_one_sample_cannot_complete_full_180_minute_validation(self) -> None:
        summary = day3.analyze(
            [sample()],
            command_used="test",
            completed=True,
            run_meta={
                "expected_sample_count": 18,
                "elapsed_seconds": 10,
                "duration_seconds": 180 * 60,
                "completion_reason": "duration_elapsed",
            },
        )

        self.assertFalse(summary["completed"])
        self.assertEqual(summary["classification"], "INCOMPLETE")
        self.assertEqual(summary["completion_reason"], "insufficient_samples")

    def test_early_interruption_is_incomplete(self) -> None:
        summary = day3.analyze(
            [sample(), sample(1)],
            command_used="test",
            completed=False,
            run_meta={
                "expected_sample_count": 18,
                "elapsed_seconds": 120,
                "duration_seconds": 180 * 60,
                "completion_reason": "interrupted",
                "interruption_reason": "received signal 15",
            },
        )

        self.assertEqual(summary["classification"], "INCOMPLETE")
        self.assertEqual(summary["interruption_reason"], "received signal 15")

    def test_completed_summary_and_handoff_match(self) -> None:
        original_handoff = day3.HANDOFF_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            day3.HANDOFF_PATH = Path(tmpdir) / "handoff.txt"
            try:
                summary = day3.analyze(
                    [sample(), sample(1), sample(2)],
                    command_used="test",
                    completed=True,
                    run_meta={
                        "expected_sample_count": 3,
                        "elapsed_seconds": 180,
                        "duration_seconds": 180,
                        "completion_reason": "duration_elapsed",
                    },
                )
                day3.write_handoff(summary)
                handoff = day3.HANDOFF_PATH.read_text()
            finally:
                day3.HANDOFF_PATH = original_handoff

        self.assertIn(f"overall result: {summary['classification']}", handoff)
        self.assertIn(f"completed: {summary['completed']}", handoff)
        self.assertNotIn("RUNNING", handoff)

    def test_duplicate_blockers_collapse_to_one(self) -> None:
        blocker = {
            "classification": "capability_blocker",
            "domain": "income",
            "root_cause": "fiverr_inbox_login_failed",
            "source": "file:fiverr_inbox.log",
            "target_key": "abc",
            "raw_window_count": 1,
        }
        summary = day3.analyze(
            [
                sample(system_health="warning", blockers=[blocker]),
                sample(1, system_health="warning", blockers=[{**blocker, "raw_window_count": 5}]),
            ],
            command_used="test",
            completed=True,
            run_meta={
                "expected_sample_count": 2,
                "elapsed_seconds": 120,
                "duration_seconds": 120,
                "completion_reason": "duration_elapsed",
            },
        )

        self.assertEqual(len(summary["noncore_blockers"]), 1)
        self.assertEqual(summary["noncore_blockers"][0]["raw_window_count"], 5)

    def test_four_repeated_stale_reliability_priorities_cannot_pass(self) -> None:
        samples = [
            sample(
                index,
                system_health="OK",
                life_kind="reliability",
                life_title="Restore system health: warning",
                life_reason="executive context reports system_health is not OK",
            )
            for index in range(4)
        ]
        summary = day3.analyze(
            samples,
            command_used="test",
            completed=True,
            run_meta={
                "expected_sample_count": 4,
                "elapsed_seconds": 240,
                "duration_seconds": 240,
                "completion_reason": "duration_elapsed",
            },
        )

        codes = {issue["code"] for issue in summary["issues"]}
        self.assertIn("stale_life_loop_health_priority", codes)
        self.assertFalse(summary["pass_criteria"]["life_loop_not_false_health_trapped"])
        self.assertEqual(summary["life_priority_health_trace"][-1]["consecutive_mismatch_count"], 4)

    def test_noncore_warning_with_repeated_reliability_priority_cannot_pass(self) -> None:
        blocker = {
            "classification": "capability_blocker",
            "domain": "income",
            "root_cause": "vast_monitor_missing_vast_package",
            "source": "file:income.log",
            "target_key": "abc",
        }
        samples = [
            sample(
                index,
                system_health="warning",
                homeostasis_status="warning",
                life_kind="reliability",
                life_title="Restore system health: warning",
                life_reason="executive context reports system_health is not OK",
                blockers=[blocker],
                active_core_count=0,
            )
            for index in range(19)
        ]

        summary = day3.analyze(
            samples,
            command_used="test",
            completed=True,
            run_meta={
                "expected_sample_count": 18,
                "elapsed_seconds": 180 * 60,
                "duration_seconds": 180 * 60,
                "completion_reason": "duration_elapsed",
            },
        )

        codes = {issue["code"] for issue in summary["issues"]}
        self.assertEqual(summary["classification"], "WARNING")
        self.assertIn("stale_life_loop_health_priority", codes)
        self.assertFalse(summary["pass_criteria"]["life_loop_not_false_health_trapped"])
        self.assertEqual(summary["life_priority_health_trace"][-1]["consecutive_mismatch_count"], 19)

    def test_one_transitional_stale_life_priority_may_pass(self) -> None:
        summary = day3.analyze(
            [
                sample(
                    system_health="OK",
                    life_kind="reliability",
                    life_title="Restore system health: warning",
                    life_reason="executive context reports system_health is not OK",
                )
            ],
            command_used="test",
            completed=True,
            run_meta={
                "expected_sample_count": 1,
                "elapsed_seconds": 60,
                "duration_seconds": 60,
                "completion_reason": "duration_elapsed",
            },
        )

        codes = {issue["code"] for issue in summary["issues"]}
        self.assertNotIn("stale_life_loop_health_priority", codes)
        self.assertTrue(summary["pass_criteria"]["life_loop_not_false_health_trapped"])
        self.assertEqual(summary["life_priority_health_trace"][0]["consecutive_mismatch_count"], 1)

    def test_two_consecutive_stale_life_priorities_warn(self) -> None:
        samples = [
            sample(
                index,
                system_health="OK",
                life_kind="reliability",
                life_title="Restore system health: warning",
                life_reason="executive context reports system_health is not OK",
            )
            for index in range(2)
        ]
        summary = day3.analyze(
            samples,
            command_used="test",
            completed=True,
            run_meta={
                "expected_sample_count": 2,
                "elapsed_seconds": 120,
                "duration_seconds": 120,
                "completion_reason": "duration_elapsed",
            },
        )

        self.assertEqual(summary["classification"], "WARNING")
        codes = {issue["code"] for issue in summary["issues"]}
        self.assertIn("stale_life_loop_health_priority", codes)
        self.assertFalse(summary["pass_criteria"]["life_loop_not_false_health_trapped"])

    def test_matching_health_and_priority_passes(self) -> None:
        summary = day3.analyze(
            [
                sample(
                    system_health="warning",
                    homeostasis_status="warning",
                    life_kind="reliability",
                    life_title="Restore system health: warning",
                    life_reason="executive context reports system_health is not OK",
                    active_core_count=1,
                ),
                sample(
                    1,
                    system_health="OK",
                    homeostasis_status="ok",
                    life_kind="work",
                    life_title="Normal work",
                    life_reason="system health is OK",
                ),
            ],
            command_used="test",
            completed=True,
            run_meta={
                "expected_sample_count": 2,
                "elapsed_seconds": 120,
                "duration_seconds": 120,
                "completion_reason": "duration_elapsed",
            },
        )

        codes = {issue["code"] for issue in summary["issues"]}
        self.assertNotIn("stale_life_loop_health_priority", codes)
        self.assertTrue(summary["pass_criteria"]["life_loop_not_false_health_trapped"])
        self.assertTrue(all(not item["mismatch"] for item in summary["life_priority_health_trace"]))


if __name__ == "__main__":
    unittest.main()
