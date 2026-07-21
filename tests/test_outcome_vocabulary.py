#!/usr/bin/env python3
"""Tests for evidence-backed outcome vocabulary."""
from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from core import narrative, outcome_loop, outcome_vocabulary


class OutcomeVocabularyTests(unittest.TestCase):
    def test_attempted_publish_is_not_rendered_as_published(self) -> None:
        claim = outcome_vocabulary.classify_outcome_evidence({
            "action_id": "devto:publish_article",
            "status": "pending",
            "evidence": "publish script started",
        })

        self.assertEqual(claim["evidence_status"], "attempted")
        rendered = outcome_vocabulary.render_outcome_claim(claim)
        self.assertIn("Attempted devto:publish_article", rendered)
        self.assertNotIn("published", rendered.lower())

    def test_blocked_action_preserves_blocker_evidence(self) -> None:
        claim = outcome_vocabulary.classify_outcome_evidence({
            "action_id": "fiverr:fulfill_order",
            "status": "failed",
            "evidence": "login failed; no 'Continue with Google' button found",
        })

        self.assertEqual(claim["evidence_status"], "blocked")
        self.assertIn("authentication_blocker", claim["evidence_types"])
        self.assertIn("login failed", claim["evidence_summary"])

    def test_vast_missing_package_is_blocked_not_success(self) -> None:
        claim = outcome_vocabulary.classify_outcome_evidence({
            "action_id": "vast:gpu_rental_monitor",
            "status": "failed",
            "evidence": "ModuleNotFoundError: No module named 'vast'",
        })

        self.assertEqual(claim["evidence_status"], "blocked")
        self.assertIn("missing_dependency", claim["evidence_types"])

    def test_failed_requires_error_evidence(self) -> None:
        claim = outcome_vocabulary.classify_outcome_evidence({
            "action_id": "api:publish",
            "status": "failed",
            "evidence": "HTTP 500 error: request failed",
        })

        self.assertEqual(claim["evidence_status"], "failed")
        self.assertIn("error", claim["evidence_types"])

    def test_open_work_is_attempted_not_failed_without_missed_execution(self) -> None:
        claim = outcome_vocabulary.classify_outcome_evidence({
            "action_id": "self_improvement:growth_requests_closed",
            "status": "failed",
            "expected_result": "memory/growth_build_requests.json has 0 open reviewed build requests.",
            "evidence": "open reviewed build requests=3 > 0",
        })

        self.assertEqual(claim["evidence_status"], "attempted")
        self.assertIn("unfinished work is not execution failure", claim["classification_reason"])

    def test_local_success_is_completed_locally_without_external_receipt(self) -> None:
        claim = outcome_vocabulary.classify_outcome_evidence({
            "action_id": "repo:checkpoint",
            "status": "succeeded",
            "evidence_type": "git_commit",
            "evidence": "local commit abc123 exists",
        })

        self.assertEqual(claim["evidence_status"], "completed_locally")
        self.assertNotEqual(claim["evidence_status"], "externally_verified")

    def test_external_verification_requires_receipt(self) -> None:
        good = {
            "action_id": "devto:publish_article",
            "evidence_status": "externally_verified",
            "evidence_types": ["post_id"],
            "post_id": "fixture-post-1",
        }
        outcome_vocabulary.validate_no_promotion(good)

        bad = {
            "action_id": "devto:publish_article",
            "evidence_status": "externally_verified",
            "evidence_types": ["local_file"],
        }
        with self.assertRaises(ValueError):
            outcome_vocabulary.validate_no_promotion(bad)

    def test_completed_locally_cannot_silently_promote_to_external_verification(self) -> None:
        local = outcome_vocabulary.classify_outcome_evidence({
            "action_id": "devto:write_article",
            "status": "succeeded",
            "evidence_type": "local_file",
            "evidence": "local markdown draft exists",
        })

        self.assertEqual(local["evidence_status"], "completed_locally")
        self.assertNotEqual(local["evidence_status"], "externally_verified")
        self.assertIsNone(local["external_receipt"])

    def test_earned_with_receipt_requires_echo_attribution(self) -> None:
        good = outcome_vocabulary.classify_outcome_evidence({
            "action_id": "income:fiverr_delivery",
            "amount": 25.0,
            "produced_by_echo": True,
            "transaction_receipt": "fixture-receipt",
        })
        self.assertEqual(good["evidence_status"], "earned_with_receipt")

        personal = outcome_vocabulary.classify_outcome_evidence({
            "action_id": "income:record_personal_income",
            "status": "succeeded",
            "source": "personal_income_record",
            "evidence_type": "local_report",
            "amount": 100.0,
            "produced_by_echo": False,
        })
        self.assertEqual(personal["evidence_status"], "completed_locally")
        self.assertFalse(personal["produced_by_echo"])

    def test_produced_by_echo_false_is_never_echo_earned_income(self) -> None:
        claim = outcome_vocabulary.classify_outcome_evidence({
            "action_id": "income:record_payment",
            "status": "succeeded",
            "amount": 100.0,
            "transaction_receipt": "fixture-receipt",
            "produced_by_echo": False,
            "evidence_type": "local_report",
        })

        self.assertNotEqual(claim["evidence_status"], "earned_with_receipt")
        self.assertFalse(claim["produced_by_echo"])

    def test_outcome_loop_report_includes_evidence_status_counts(self) -> None:
        report = outcome_loop.build_report([
            {
                "action_id": "fixture:local",
                "category": "fixture",
                "status": "succeeded",
                "score": 1.0,
                "expected_result": "fixture report exists",
                "evidence": "fixture report exists",
                "last_checked_at": "2026-07-20T10:00:00+00:00",
            },
            {
                "action_id": "fixture:blocked",
                "category": "fixture",
                "status": "failed",
                "score": -1.0,
                "expected_result": "fixture login completes",
                "evidence": "captcha blocked completion",
                "last_checked_at": "2026-07-20T10:00:00+00:00",
            },
        ], executive_context={"current_objective": "fixture"})

        counts = report["summary"]["evidence_status_counts"]
        self.assertEqual(counts["completed_locally"], 1)
        self.assertEqual(counts["blocked"], 1)
        self.assertEqual(report["records"][0]["evidence_status"], "completed_locally")

    def test_markdown_summary_uses_evidence_backed_language(self) -> None:
        report = outcome_loop.build_report([
            {
                "action_id": "devto:publish_article",
                "category": "content",
                "status": "pending",
                "score": 0.0,
                "expected_result": "article is live",
                "evidence": "publish script started",
                "last_checked_at": "2026-07-20T10:00:00+00:00",
            }
        ], executive_context={"current_objective": "devto"})

        original = outcome_loop.REPORT_MD
        with tempfile.TemporaryDirectory() as tmpdir:
            outcome_loop.REPORT_MD = Path(tmpdir) / "outcome_loop_report.md"
            try:
                outcome_loop.write_markdown(report)
                text = outcome_loop.REPORT_MD.read_text()
            finally:
                outcome_loop.REPORT_MD = original

        self.assertIn("attempted", text.lower())
        self.assertNotIn("published an article", text.lower())

    def test_raw_succeeded_cannot_render_as_external_or_earned_by_itself(self) -> None:
        report = outcome_loop.build_report([
            {
                "action_id": "devto:publish_article",
                "category": "content",
                "status": "succeeded",
                "score": 1.0,
                "expected_result": "article is live",
                "evidence": "raw succeeded counter only",
                "last_checked_at": "2026-07-20T10:00:00+00:00",
            },
            {
                "action_id": "income:earn_money",
                "category": "income",
                "status": "succeeded",
                "score": 1.0,
                "expected_result": "money earned",
                "evidence": "raw succeeded counter only",
                "last_checked_at": "2026-07-20T10:00:00+00:00",
            },
        ], executive_context={"current_objective": "fixture"})

        rendered = "\n".join(record["evidence_backed_summary"].lower() for record in report["records"])
        self.assertIn("completed locally", rendered)
        self.assertNotIn("externally verified", rendered)
        self.assertNotIn("earned income with a transaction receipt", rendered)

    def test_narrative_guidance_contains_outcome_vocabulary(self) -> None:
        self.assertIn("externally verified", narrative.SYSTEM.lower())
        self.assertIn("earned with receipt", narrative.SYSTEM.lower())
        self.assertIn("raw succeeded or failed counters are never authoritative", narrative.SYSTEM.lower())

    def test_narrative_uses_evidence_status_claims_for_outcomes(self) -> None:
        original = narrative.OUTCOME_REPORT
        with tempfile.TemporaryDirectory() as tmpdir:
            narrative.OUTCOME_REPORT = Path(tmpdir) / "outcome_loop_report.json"
            narrative.OUTCOME_REPORT.write_text(json.dumps({
                "records": [
                    {
                        "action_id": "devto:publish_article",
                        "evidence_status": "attempted",
                        "evidence_backed_summary": "Attempted devto:publish_article; success is not proven.",
                    }
                ]
            }))
            try:
                claims = narrative._recent_outcome_claims()
            finally:
                narrative.OUTCOME_REPORT = original

        self.assertEqual(len(claims), 1)
        self.assertIn("evidence_status=attempted", claims[0])
        self.assertIn("success is not proven", claims[0])

    def test_no_automatic_task_or_structured_fact_creation_api_exists(self) -> None:
        exported = set(dir(outcome_vocabulary))
        self.assertNotIn("create_task", exported)
        self.assertNotIn("create_structured_fact", exported)


if __name__ == "__main__":
    unittest.main()
