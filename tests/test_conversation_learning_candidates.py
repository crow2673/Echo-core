from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from core import conversation_learning_candidates as clc


class ConversationLearningCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.candidates = root / "candidates.jsonl"
        self.events = root / "events.jsonl"
        self.approved = root / "reviewed.jsonl"

    def _capture(self, **overrides):
        payload = {
            "andrew_message": "What is going on around you?",
            "echo_response": "Trading bots are running smoothly.",
            "source": "telegram",
            "channel": "telegram",
            "source_interaction_ids": [101, 102],
            "model_used": "qwen2.5:7b",
            "candidate_path": self.candidates,
            "events_path": self.events,
        }
        payload.update(overrides)
        return clc.capture_candidate(**payload)

    def test_raw_conversation_becomes_pending_candidate_not_approved_training(self) -> None:
        candidate = self._capture()

        self.assertEqual(candidate["status"], "pending_review")
        self.assertIn("trading", candidate["echo_response"].lower())
        self.assertTrue(candidate["operational_claim_flags"])
        self.assertEqual(clc.approved_training_examples(self.candidates), [])

    def test_deduplication_returns_existing_candidate(self) -> None:
        first = self._capture()
        second = self._capture()

        self.assertEqual(first["candidate_id"], second["candidate_id"])
        self.assertEqual(len(clc.list_candidates(self.candidates)), 1)

    def test_private_content_is_excluded(self) -> None:
        candidate = self._capture(
            andrew_message="my api_key is fixture-secret",
            echo_response="I saved the token.",
        )

        self.assertEqual(candidate["status"], "excluded")
        self.assertEqual(candidate["privacy_classification"], "excluded_private")

    def test_review_history_is_append_only_and_preserves_original(self) -> None:
        candidate = self._capture()
        reviewed = clc.review_candidate(
            candidate["candidate_id"],
            decision="corrected",
            reviewer="Andrew",
            reason="remove unsupported operational claim",
            corrected_echo_response="I have modules for trading experiments, but no verified success is present.",
            candidate_path=self.candidates,
            events_path=self.events,
        )

        self.assertEqual(reviewed["status"], "corrected")
        self.assertEqual(reviewed["echo_response"], "Trading bots are running smoothly.")
        self.assertIn("trading experiments", reviewed["corrected_echo_response"])
        events = [json.loads(line) for line in self.events.read_text().splitlines()]
        self.assertEqual([event["event"] for event in events], ["captured", "review"])
        self.assertEqual(events[-1]["previous_status"], "pending_review")
        self.assertEqual(events[-1]["resulting_status"], "corrected")

    def test_only_approved_or_corrected_candidates_export_to_dataset(self) -> None:
        candidate = self._capture(echo_response="I can talk through the system state carefully.")
        clc.capture_candidate(
            andrew_message="Private fixture password is abc",
            echo_response="I saw it.",
            source="telegram",
            candidate_path=self.candidates,
            events_path=self.events,
        )
        clc.review_candidate(
            candidate["candidate_id"],
            decision="approved",
            reviewer="Andrew",
            reason="useful careful response",
            candidate_path=self.candidates,
            events_path=self.events,
        )

        report = clc.export_approved_dataset(candidate_path=self.candidates, output_path=self.approved)
        rows = [json.loads(line) for line in self.approved.read_text().splitlines()]
        self.assertEqual(report["approved_examples"], 1)
        self.assertEqual(rows[0]["source"], "reviewed_conversation_learning")

    def test_rejected_candidate_cannot_be_silently_approved(self) -> None:
        candidate = self._capture()
        clc.review_candidate(
            candidate["candidate_id"],
            decision="rejected",
            reviewer="Andrew",
            reason="bad example",
            candidate_path=self.candidates,
            events_path=self.events,
        )

        with self.assertRaises(ValueError):
            clc.review_candidate(
                candidate["candidate_id"],
                decision="approved",
                reviewer="Andrew",
                reason="changed mind without explicit reopen",
                candidate_path=self.candidates,
                events_path=self.events,
            )

    def test_blocked_or_failed_response_is_not_success_category(self) -> None:
        candidate = self._capture(
            echo_response="Publishing was blocked by captcha, so the article is not externally verified.",
            evidence_status="blocked",
        )

        self.assertEqual(candidate["status"], "pending_review")
        self.assertEqual(candidate["evidence_status"], "blocked")
        self.assertNotEqual(candidate["review_category"], "successful_behavior_worth_reinforcing")

    def test_telegram_preserves_ledger_semantic_memory_and_candidate_capture(self) -> None:
        source = Path("core/telegram_intake.py").read_text()

        self.assertIn('record("andrew"', source)
        self.assertIn("remember_exchange(text, response, \"telegram\")", source)
        self.assertIn("capture_candidate(", source)
        self.assertNotIn('memory/finetune_dataset.jsonl"\n                    entry = {"conversations"', source)

    def test_trainer_no_longer_falls_back_to_raw_chat_dataset(self) -> None:
        source = Path("tools/finetune_train.py").read_text()

        self.assertIn("finetune_dataset_reviewed.jsonl", source)
        self.assertNotIn('return BASE / "memory/finetune_dataset.jsonl"', source)

    def test_environment_paths_support_private_runtime_storage(self) -> None:
        os.environ["ECHO_CONVERSATION_LEARNING_CANDIDATES"] = str(self.candidates)
        os.environ["ECHO_CONVERSATION_LEARNING_EVENTS"] = str(self.events)
        self.addCleanup(os.environ.pop, "ECHO_CONVERSATION_LEARNING_CANDIDATES", None)
        self.addCleanup(os.environ.pop, "ECHO_CONVERSATION_LEARNING_EVENTS", None)

        candidate = clc.capture_candidate(
            andrew_message="Fixture message",
            echo_response="Fixture response that needs review.",
            source="test",
        )

        self.assertTrue(self.candidates.exists())
        self.assertEqual(candidate["status"], "pending_review")


if __name__ == "__main__":
    unittest.main()
