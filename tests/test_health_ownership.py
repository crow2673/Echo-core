#!/usr/bin/env python3
"""Tests for operational health ownership boundaries."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import executive_context
from core.homeostasis import collect_findings, operational_system_health, report_status
from tools import operational_audit
from tools.operational_audit import assess


def _base_report() -> dict:
    return {
        "systemd": {
            "critical_units": {
                "echo-core.service": "active",
                "echo-governor-v2.timer": "active",
                "echo-circuit-breaker.timer": "active",
                "echo-telegram-intake.timer": "active",
                "echo-self-act-worker.timer": "active",
                "echo-conductor-agents-repair.timer": "active",
            },
            "failed_units": [],
        },
        "echo_state": {"exists": True, "age_seconds": 10, "cascade_error": None},
        "imports": {},
        "venvs": [],
        "sprawl": {"big_logs_over_100mb": [], "active_text_memory_file_count": 1},
        "generated_apps": {"count": 0, "with_deploy_error": []},
    }


class HealthOwnershipTests(unittest.TestCase):
    def test_failed_service_creates_operational_error(self) -> None:
        report = _base_report()
        report["systemd"]["failed_units"] = ["echo-broken.service"]
        assessment = assess(report)
        findings = collect_findings({"assessment": assessment})

        self.assertEqual(assessment["status"], "critical")
        self.assertEqual(report_status(findings), "critical")
        self.assertTrue(any("echo-broken.service" in item["message"] for item in findings))

    def test_generated_app_count_alone_is_maintenance_not_health_warning(self) -> None:
        report = _base_report()
        report["generated_apps"]["count"] = 60
        assessment = assess(report)

        self.assertEqual(assessment["status"], "ok")
        self.assertEqual(assessment["warnings"], [])
        self.assertIn("generated app inventory growth: 60 apps", assessment["maintenance"])

    def test_noncore_warning_does_not_downgrade_operational_system_health(self) -> None:
        report = {
            "status": "warning",
            "findings": [
                {
                    "kind": "needs_andrew",
                    "severity": "warning",
                    "message": "stale worker requires review: trader",
                    "unit": "echo-trader.service",
                }
            ],
            "capability_blockers": [
                {
                    "classification": "capability_blocker",
                    "domain": "income",
                    "root_cause": "fiverr_inbox_login_failed",
                    "active": True,
                }
            ],
            "maintenance_findings": ["generated app inventory growth: 65 apps"],
            "anomaly_summary": {"active_core_operational_count": 0},
        }

        self.assertEqual(operational_system_health(report), "OK")

    def test_life_loop_source_cannot_overwrite_authoritative_health(self) -> None:
        original_path = executive_context.CONTEXT_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            executive_context.CONTEXT_PATH = Path(tmpdir) / "executive_context.json"
            try:
                executive_context.safe_update(
                    {"system_health": "OK"},
                    source="homeostasis",
                    reason="test authoritative health",
                )
                executive_context.safe_update(
                    {"system_health": "critical", "current_focus": "test focus"},
                    source="life_loop",
                    reason="life loop should not own health",
                )
                context = executive_context.load_context(create=False)
            finally:
                executive_context.CONTEXT_PATH = original_path

        self.assertEqual(context["system_health"], "OK")
        self.assertEqual(context["current_focus"], "test focus")

    def test_local_only_mode_removes_only_conductor_repair_from_critical_units(self) -> None:
        original = operational_audit.local_only_mode_enabled
        operational_audit.local_only_mode_enabled = lambda: True
        try:
            units = operational_audit.critical_units_for_mode()
        finally:
            operational_audit.local_only_mode_enabled = original

        self.assertNotIn("echo-conductor-agents-repair.timer", units)
        self.assertIn("echo-core.service", units)
        self.assertIn("echo-telegram-intake.timer", units)

    def test_local_only_mode_disabled_repair_is_maintenance_not_critical(self) -> None:
        report = _base_report()
        report["local_only_mode"] = True
        report["systemd"]["critical_units"].pop("echo-conductor-agents-repair.timer")

        assessment = assess(report)

        self.assertEqual(assessment["status"], "ok")
        self.assertEqual(assessment["critical"], [])
        self.assertIn(
            "local-only mode: Claude/Codex conductor repair intentionally disabled",
            assessment["maintenance"],
        )

    def test_disabled_finetune_timer_is_not_a_core_failure(self) -> None:
        report = _base_report()
        report["local_only_mode"] = True

        assessment = assess(report)

        self.assertEqual(assessment["status"], "ok")
        self.assertFalse(any("finetune" in item for item in assessment["critical"]))

    def test_unavailable_claude_codex_agents_are_not_core_failures_in_local_mode(self) -> None:
        report = _base_report()
        report["local_only_mode"] = True
        report["systemd"]["critical_units"].pop("echo-conductor-agents-repair.timer")

        assessment = assess(report)

        self.assertEqual(assessment["status"], "ok")
        self.assertFalse(any("Claude" in item or "Codex" in item for item in assessment["critical"]))

    def test_local_only_mode_still_reports_unexpected_core_failure(self) -> None:
        report = _base_report()
        report["local_only_mode"] = True
        report["systemd"]["critical_units"].pop("echo-conductor-agents-repair.timer")
        report["systemd"]["critical_units"]["echo-core.service"] = "inactive"

        assessment = assess(report)

        self.assertEqual(assessment["status"], "critical")
        self.assertIn("critical unit not active: echo-core.service=inactive", assessment["critical"])


if __name__ == "__main__":
    unittest.main()
