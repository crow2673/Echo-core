#!/usr/bin/env python3
"""Tests for Life Loop priority invalidation and core health gating."""
from __future__ import annotations

import unittest

from core import life_loop


def evidence(system_health: str = "OK", homeostasis: dict | None = None) -> dict:
    return {
        "executive_context": {
            "system_health": system_health,
            "active_blocker": None,
        },
        "homeostasis": homeostasis or {
            "status": "ok",
            "findings": [],
            "needs_andrew": [],
            "capability_blockers": [],
            "maintenance_findings": [],
            "anomaly_summary": {"active_core_operational_count": 0},
        },
        "autonomy_model": {},
        "income_ledger": {"channels": [], "summary": {}},
        "build_requests": [],
        "growth": [],
    }


class LifeLoopPriorityTests(unittest.TestCase):
    def test_health_warning_priority_clears_when_core_health_is_ok(self) -> None:
        priority = life_loop.choose_priority(evidence(system_health="warning"))

        self.assertNotEqual(priority["kind"], "reliability")
        self.assertNotIn("Restore system health", priority["title"])

    def test_active_core_failure_preserves_reliability_priority(self) -> None:
        priority = life_loop.choose_priority(evidence(
            system_health="OK",
            homeostasis={
                "status": "warning",
                "findings": [
                    {
                        "classification": "core_operational",
                        "severity": "warning",
                        "message": "active core log anomaly incidents",
                    }
                ],
                "needs_andrew": [],
                "anomaly_summary": {"active_core_operational_count": 1},
            },
        ))

        self.assertEqual(priority["kind"], "reliability")
        self.assertIn("Restore system health", priority["title"])

    def test_capability_blockers_alone_do_not_preserve_reliability_priority(self) -> None:
        priority = life_loop.choose_priority(evidence(
            system_health="warning",
            homeostasis={
                "status": "warning",
                "findings": [],
                "needs_andrew": [],
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
            },
        ))

        self.assertNotEqual(priority["kind"], "reliability")
        self.assertNotIn("Restore system health", priority["title"])


if __name__ == "__main__":
    unittest.main()
