#!/usr/bin/env python3
"""Tests for log anomaly deduplication and health-domain classification."""
from __future__ import annotations

import unittest

from core import homeostasis
from core.life_loop import choose_priority


class AnomalyHealthClassificationTests(unittest.TestCase):
    def test_overlapping_windows_deduplicate_to_one_incident(self) -> None:
        windows = [
            {
                "source": "file:income.log",
                "target_key": "vast-key",
                "template": "[<NUM><NUM><NUM> <TIME>] [vast] CLI error: Traceback (most recent call last):",
                "detected_at": f"2026-07-10T14:{minute:02d}:00+00:00",
            }
            for minute in range(27)
        ]

        incidents = homeostasis._group_anomaly_incidents(windows)

        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["raw_window_count"], 27)
        self.assertEqual(incidents[0]["unique_incident_count"] if "unique_incident_count" in incidents[0] else 1, 1)
        self.assertEqual(incidents[0]["classification"], "capability_blocker")

    def test_historical_failed_unit_log_does_not_downgrade_when_unit_healthy(self) -> None:
        original = homeostasis.unit_is_failed
        homeostasis.unit_is_failed = lambda unit: False
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:system_health.log",
                "failed-unit-key",
                "<TS> host systemd[<PID>]: Failed to start echo-log-anomaly.service - Echo Log Anomaly Scorer.",
            )
        finally:
            homeostasis.unit_is_failed = original

        self.assertEqual(incident["classification"], "resolved_historical")
        self.assertFalse(incident["active"])
        self.assertEqual(homeostasis.report_status([incident]), "ok")

    def test_vast_and_fiverr_remain_active_capability_blockers(self) -> None:
        vast = homeostasis._classify_anomaly_incident(
            "file:income.log",
            "vast-key",
            "[<NUM><NUM><NUM> <TIME>] [vast] CLI error: Traceback (most recent call last):",
        )
        fiverr = homeostasis._classify_anomaly_incident(
            "file:fiverr_fulfiller.log",
            "fiverr-key",
            "[fiverr_fulfiller] login failed",
        )

        self.assertEqual(vast["classification"], "capability_blocker")
        self.assertEqual(vast["domain"], "income")
        self.assertTrue(vast["active"])
        self.assertEqual(fiverr["classification"], "capability_blocker")
        self.assertEqual(fiverr["domain"], "income")
        self.assertTrue(fiverr["active"])

    def test_capability_blockers_alone_leave_system_health_ok(self) -> None:
        blocker = {
            "kind": "warning",
            "severity": "warning",
            "classification": "capability_blocker",
            "message": "Fiverr login failed",
        }

        self.assertEqual(homeostasis.report_status([blocker]), "ok")

    def test_failed_core_service_produces_warning(self) -> None:
        original = homeostasis.unit_is_failed
        homeostasis.unit_is_failed = lambda unit: unit == "echo-core.service"
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:system_health.log",
                "failed-core-key",
                "<TS> host systemd[<PID>]: Failed to start echo-core.service - Echo Core.",
            )
        finally:
            homeostasis.unit_is_failed = original

        finding = {
            "kind": "warning",
            "severity": "warning",
            **incident,
        }
        self.assertEqual(incident["classification"], "core_operational")
        self.assertTrue(incident["active"])
        self.assertEqual(homeostasis.report_status([finding]), "warning")

    def test_stale_life_loop_restore_health_text_does_not_downgrade_ok_health(self) -> None:
        original_failed = homeostasis.unit_is_failed
        homeostasis.unit_is_failed = lambda unit: False
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:life_loop.log",
                "life-restore-key",
                "life_loop health=critical priority=reliability: Restore system health: critical dry_run=False",
            )
        finally:
            homeostasis.unit_is_failed = original_failed

        self.assertEqual(incident["classification"], "resolved_historical")
        self.assertFalse(incident["active"])
        self.assertEqual(homeostasis.report_status([incident]), "ok")

    def test_current_active_core_failure_still_downgrades_health(self) -> None:
        original_failed = homeostasis.unit_is_failed
        homeostasis.unit_is_failed = lambda unit: unit == "echo-life-loop.service"
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:life_loop.log",
                "life-restore-key",
                "life_loop health=critical priority=reliability: Restore system health: critical dry_run=False",
            )
        finally:
            homeostasis.unit_is_failed = original_failed

        finding = {"kind": "warning", "severity": "warning", **incident}
        self.assertEqual(incident["classification"], "core_operational")
        self.assertTrue(incident["active"])
        self.assertEqual(homeostasis.report_status([finding]), "warning")

    def test_one_telegram_429_remains_transient(self) -> None:
        original_failed = homeostasis.unit_is_failed
        original_active = homeostasis.unit_is_active
        original_success = homeostasis.telegram_success_after
        homeostasis.unit_is_failed = lambda unit: False
        homeostasis.unit_is_active = lambda unit: True
        homeostasis.telegram_success_after = lambda timestamp: False
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:telegram_intake.log",
                "tg-429",
                "[telegram] fetch error: HTTP Error <NUM>: Too Many Requests",
                raw_window_count=1,
                last_seen="2026-07-13T22:00:30+00:00",
            )
        finally:
            homeostasis.unit_is_failed = original_failed
            homeostasis.unit_is_active = original_active
            homeostasis.telegram_success_after = original_success

        self.assertEqual(incident["classification"], "transient")
        self.assertTrue(incident["active"])
        self.assertEqual(homeostasis.report_status([{"kind": "warning", "severity": "warning", **incident}]), "ok")

    def test_one_telegram_ssl_timeout_remains_transient(self) -> None:
        original_failed = homeostasis.unit_is_failed
        original_active = homeostasis.unit_is_active
        original_success = homeostasis.telegram_success_after
        homeostasis.unit_is_failed = lambda unit: False
        homeostasis.unit_is_active = lambda unit: True
        homeostasis.telegram_success_after = lambda timestamp: False
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:telegram_intake.log",
                "tg-ssl",
                "[telegram] fetch error: <urlopen error _ssl.c:<NUM>: The handshake operation timed out>",
                raw_window_count=1,
                last_seen="2026-07-13T22:00:30+00:00",
            )
        finally:
            homeostasis.unit_is_failed = original_failed
            homeostasis.unit_is_active = original_active
            homeostasis.telegram_success_after = original_success

        self.assertEqual(incident["classification"], "transient")
        self.assertTrue(incident["active"])

    def test_successful_later_telegram_poll_resolves_transient_incident(self) -> None:
        original_failed = homeostasis.unit_is_failed
        original_active = homeostasis.unit_is_active
        original_success = homeostasis.telegram_success_after
        homeostasis.unit_is_failed = lambda unit: False
        homeostasis.unit_is_active = lambda unit: True
        homeostasis.telegram_success_after = lambda timestamp: True
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:telegram_intake.log",
                "tg-timeout",
                "[telegram] fetch error: The read operation timed out",
                raw_window_count=1,
                last_seen="2026-07-13T22:00:30+00:00",
            )
        finally:
            homeostasis.unit_is_failed = original_failed
            homeostasis.unit_is_active = original_active
            homeostasis.telegram_success_after = original_success

        self.assertEqual(incident["classification"], "transient")
        self.assertFalse(incident["active"])
        self.assertTrue(incident["success_after_incident"])
        self.assertEqual(incident["lifecycle_state"], "recovered_transient")

    def test_one_telegram_502_with_later_success_resolves_transient_incident(self) -> None:
        original_failed = homeostasis.unit_is_failed
        original_active = homeostasis.unit_is_active
        original_success = homeostasis.telegram_success_after
        homeostasis.unit_is_failed = lambda unit: False
        homeostasis.unit_is_active = lambda unit: True
        homeostasis.telegram_success_after = lambda timestamp: True
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:telegram_intake.log",
                "tg-502",
                "[telegram] fetch error: HTTP Error 502: Bad Gateway",
                raw_window_count=1,
                last_seen="2026-07-27T20:10:49-05:00",
            )
        finally:
            homeostasis.unit_is_failed = original_failed
            homeostasis.unit_is_active = original_active
            homeostasis.telegram_success_after = original_success

        self.assertEqual(incident["classification"], "transient")
        self.assertFalse(incident["active"])
        self.assertEqual(incident["lifecycle_state"], "recovered_transient")
        self.assertTrue(incident["success_after_incident"])

    def test_stale_telegram_log_rescan_preserves_source_timestamp(self) -> None:
        original_failed = homeostasis.unit_is_failed
        original_active = homeostasis.unit_is_active
        original_success = homeostasis.telegram_success_after
        original_record = homeostasis._record_incident_lifecycle_events
        homeostasis.unit_is_failed = lambda unit: False
        homeostasis.unit_is_active = lambda unit: True
        homeostasis.telegram_success_after = lambda timestamp: timestamp == "2026-07-27T20:10:49-05:00"
        homeostasis._record_incident_lifecycle_events = lambda incidents: None
        try:
            incidents = homeostasis._group_anomaly_incidents([
                {
                    "source": "file:telegram_intake.log",
                    "target_key": "tg-502",
                    "template": "[telegram] fetch error: HTTP Error 502: Bad Gateway",
                    "ts": "2026-07-27T20:10:49-05:00",
                    "detected_at": "2026-07-28T17:46:00+00:00",
                }
            ])
        finally:
            homeostasis.unit_is_failed = original_failed
            homeostasis.unit_is_active = original_active
            homeostasis.telegram_success_after = original_success
            homeostasis._record_incident_lifecycle_events = original_record

        self.assertEqual(len(incidents), 1)
        incident = incidents[0]
        self.assertEqual(incident["first_seen"], "2026-07-27T20:10:49-05:00")
        self.assertEqual(incident["last_seen"], "2026-07-27T20:10:49-05:00")
        self.assertEqual(incident["source_last_seen"], "2026-07-27T20:10:49-05:00")
        self.assertEqual(incident["scan_last_seen"], "2026-07-28T17:46:00+00:00")
        self.assertEqual(incident["classification"], "transient")
        self.assertFalse(incident["active"])

    def test_briefing_warmup_timeout_with_later_success_is_transient(self) -> None:
        original_failed = homeostasis.unit_is_failed
        original_success = homeostasis.briefing_success_after
        homeostasis.unit_is_failed = lambda unit: False
        homeostasis.briefing_success_after = lambda timestamp: True
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:briefing.log",
                "briefing-timeout",
                "[router] call_ollama error (qwen2.<NUM>:32b): timed out",
                raw_window_count=1,
                last_seen="2026-07-16T13:39:01+00:00",
            )
        finally:
            homeostasis.unit_is_failed = original_failed
            homeostasis.briefing_success_after = original_success

        self.assertEqual(incident["classification"], "transient")
        self.assertFalse(incident["active"])
        self.assertEqual(homeostasis.report_status([{"kind": "warning", "severity": "warning", **incident}]), "ok")

    def test_briefing_timeout_without_later_success_is_capability_blocker(self) -> None:
        original_failed = homeostasis.unit_is_failed
        original_success = homeostasis.briefing_success_after
        homeostasis.unit_is_failed = lambda unit: False
        homeostasis.briefing_success_after = lambda timestamp: False
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:briefing.log",
                "briefing-timeout",
                "[router] call_ollama error (qwen2.<NUM>:32b): timed out",
                raw_window_count=1,
                last_seen="2026-07-16T13:39:01+00:00",
            )
        finally:
            homeostasis.unit_is_failed = original_failed
            homeostasis.briefing_success_after = original_success

        self.assertEqual(incident["classification"], "capability_blocker")
        self.assertTrue(incident["active"])

    def test_current_telegram_service_failure_remains_core_operational(self) -> None:
        original_failed = homeostasis.unit_is_failed
        original_active = homeostasis.unit_is_active
        original_success = homeostasis.telegram_success_after
        homeostasis.unit_is_failed = lambda unit: unit == "echo-telegram-intake.service"
        homeostasis.unit_is_active = lambda unit: True
        homeostasis.telegram_success_after = lambda timestamp: False
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:telegram_intake.log",
                "tg-502",
                "[telegram] fetch error: HTTP Error 502: Bad Gateway",
                raw_window_count=1,
                last_seen="2026-07-28T12:46:00-05:00",
            )
        finally:
            homeostasis.unit_is_failed = original_failed
            homeostasis.unit_is_active = original_active
            homeostasis.telegram_success_after = original_success

        self.assertEqual(incident["classification"], "core_operational")
        self.assertTrue(incident["active"])
        self.assertEqual(homeostasis.report_status([{"kind": "warning", "severity": "warning", **incident}]), "warning")

    def test_briefing_timeout_with_failed_service_is_core_operational(self) -> None:
        original_failed = homeostasis.unit_is_failed
        original_success = homeostasis.briefing_success_after
        homeostasis.unit_is_failed = lambda unit: unit == "echo-daily-briefing.service"
        homeostasis.briefing_success_after = lambda timestamp: False
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:briefing.log",
                "briefing-timeout",
                "[router] call_ollama error (qwen2.<NUM>:32b): timed out",
                raw_window_count=1,
                last_seen="2026-07-16T13:39:01+00:00",
            )
        finally:
            homeostasis.unit_is_failed = original_failed
            homeostasis.briefing_success_after = original_success

        self.assertEqual(incident["classification"], "core_operational")
        self.assertTrue(incident["active"])
        self.assertEqual(homeostasis.report_status([{"kind": "warning", "severity": "warning", **incident}]), "warning")

    def test_repeated_persistent_telegram_failures_escalate(self) -> None:
        original_failed = homeostasis.unit_is_failed
        original_active = homeostasis.unit_is_active
        original_success = homeostasis.telegram_success_after
        homeostasis.unit_is_failed = lambda unit: False
        homeostasis.unit_is_active = lambda unit: True
        homeostasis.telegram_success_after = lambda timestamp: False
        try:
            incident = homeostasis._classify_anomaly_incident(
                "file:telegram_intake.log",
                "tg-timeout",
                "[telegram] fetch error: The read operation timed out",
                raw_window_count=homeostasis.TELEGRAM_TRANSIENT_ESCALATE_WINDOWS,
                last_seen="2026-07-13T22:00:30+00:00",
            )
        finally:
            homeostasis.unit_is_failed = original_failed
            homeostasis.unit_is_active = original_active
            homeostasis.telegram_success_after = original_success

        self.assertEqual(incident["classification"], "capability_blocker")
        self.assertTrue(incident["active"])
        self.assertEqual(incident["root_cause"], "telegram_recurring_degraded_condition")
        self.assertEqual(incident["lifecycle_state"], "recurring_degraded")

    def test_telegram_auth_failure_is_not_harmless_transient_noise(self) -> None:
        incident = homeostasis._classify_anomaly_incident(
            "file:telegram_intake.log",
            "tg-auth",
            "[telegram] fetch error: HTTP Error 401: Unauthorized",
        )

        self.assertEqual(incident["classification"], "capability_blocker")
        self.assertEqual(incident["root_cause"], "telegram_auth_or_config_failure")
        self.assertTrue(incident["active"])

    def test_capability_and_transient_findings_alone_leave_system_health_ok(self) -> None:
        report = {
            "findings": [
                {"kind": "warning", "severity": "warning", "classification": "transient", "message": "telegram 429"},
                {"kind": "warning", "severity": "warning", "classification": "capability_blocker", "message": "telegram auth"},
            ],
            "anomaly_summary": {"active_core_operational_count": 0},
        }

        self.assertEqual(homeostasis.report_status(report["findings"]), "ok")
        self.assertEqual(homeostasis.operational_system_health(report), "OK")

    def test_life_loop_prioritizes_normally_while_exposing_income_blockers(self) -> None:
        evidence = {
            "executive_context": {"system_health": "OK"},
            "homeostasis": {
                "status": "ok",
                "findings": [],
                "needs_andrew": [],
                "capability_blockers": [
                    {"classification": "capability_blocker", "domain": "income", "message": "Vast missing module"}
                ],
            },
            "autonomy_model": {
                "next_priority": {
                    "kind": "zero_human_action",
                    "title": "Run useful local audit",
                    "reason": "available local work",
                    "next_step": "Run the audit.",
                }
            },
            "income_ledger": {"channels": []},
            "build_requests": [],
            "growth": [],
        }

        priority = choose_priority(evidence)

        self.assertEqual(priority["kind"], "zero_human_action")
        self.assertNotEqual(priority["kind"], "reliability")


if __name__ == "__main__":
    unittest.main()
