#!/usr/bin/env python3
"""Tests for staged offsite backup transport reliability."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core import homeostasis
from tools import offsite_backup


class OffsiteBackupTransportTests(unittest.TestCase):
    def test_archive_failure_is_critical_stage_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(offsite_backup.tarfile, "open", side_effect=OSError("disk full")):
                with self.assertRaises(offsite_backup.BackupStageError):
                    offsite_backup.create_archive("20260713_1200", Path(tmpdir))

    def test_encryption_failure_is_critical_stage_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir) / "echo_backup_test.tar.gz"
            archive.write_bytes(b"archive")
            failed = SimpleNamespace(returncode=1, stderr="bad passphrase")
            with mock.patch.object(offsite_backup.subprocess, "run", return_value=failed):
                with self.assertRaises(offsite_backup.BackupStageError):
                    offsite_backup.encrypt_archive(archive, "secret", pending_dir=Path(tmpdir) / "pending")

    def test_transient_smtp_timeout_preserves_artifact_and_is_not_core_critical(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            artifact = base / "memory/offsite_backups/pending/echo_backup_test.tar.gz.gpg"
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"encrypted")
            status_path = base / "memory/offsite_backup_status.json"
            original_base = homeostasis.BASE
            original_loader = homeostasis.load_json
            try:
                homeostasis.BASE = base
                status_path.write_text(
                    """
                    {
                      "local_backup_created": true,
                      "encryption_completed": true,
                      "offsite_delivery_pending": true,
                      "offsite_delivery_succeeded": false,
                      "delivery_attempts": 1,
                      "max_delivery_attempts": 3,
                      "artifact_path": "memory/offsite_backups/pending/echo_backup_test.tar.gz.gpg",
                      "last_error": "SMTP timeout"
                    }
                    """
                )
                homeostasis.load_json = lambda path, default: original_loader(path, default)
                finding = homeostasis.offsite_backup_finding()
            finally:
                homeostasis.BASE = original_base
                homeostasis.load_json = original_loader

        self.assertEqual(finding["classification"], "capability_blocker")
        self.assertEqual(finding["severity"], "info")
        self.assertEqual(homeostasis.report_status([finding]), "ok")
        self.assertEqual(
            homeostasis.operational_system_health(
                {"findings": [finding], "anomaly_summary": {"active_core_operational_count": 0}}
            ),
            "OK",
        )

    def test_repeated_transport_failures_escalate_to_warning_not_critical(self) -> None:
        status = {
            "delivery_attempts": 3,
            "max_delivery_attempts": 3,
            "updated_at": "2026-07-13T12:00:00+00:00",
        }
        self.assertTrue(homeostasis.offsite_backup_delivery_escalated(status))

    def test_successful_resend_clears_blocker_and_moves_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            pending = base / "memory/offsite_backups/pending"
            sent = base / "memory/offsite_backups/sent"
            artifact = pending / "echo_backup_test.tar.gz.gpg"
            pending.mkdir(parents=True)
            artifact.write_bytes(b"encrypted")
            status = {
                "stamp": "20260713_1200",
                "files_added": 1,
                "artifact_path": "memory/offsite_backups/pending/echo_backup_test.tar.gz.gpg",
                "local_backup_created": True,
                "encryption_completed": True,
                "offsite_delivery_pending": True,
                "delivery_attempts": 0,
            }
            originals = (
                offsite_backup.BASE,
                offsite_backup.STATUS_PATH,
                offsite_backup.PENDING_DIR,
                offsite_backup.SENT_DIR,
                offsite_backup.LAST_BACKUP_FILE,
            )
            try:
                offsite_backup.BASE = base
                offsite_backup.STATUS_PATH = base / "memory/offsite_backup_status.json"
                offsite_backup.PENDING_DIR = pending
                offsite_backup.SENT_DIR = sent
                offsite_backup.LAST_BACKUP_FILE = base / "memory/offsite_backup_last.txt"
                with mock.patch.object(offsite_backup, "send_gmail", return_value=None):
                    result = offsite_backup.deliver_with_retries(
                        status,
                        {"GMAIL_ADDRESS": "a@example.com", "GMAIL_APP_PASSWORD": "pw"},
                        sleep_between_retries=False,
                    )
            finally:
                (
                    offsite_backup.BASE,
                    offsite_backup.STATUS_PATH,
                    offsite_backup.PENDING_DIR,
                    offsite_backup.SENT_DIR,
                    offsite_backup.LAST_BACKUP_FILE,
                ) = originals

        self.assertTrue(result["offsite_delivery_succeeded"])
        self.assertFalse(result["offsite_delivery_pending"])
        self.assertIn("sent/echo_backup_test.tar.gz.gpg", result["artifact_path"])

    def test_duplicate_sends_are_prevented(self) -> None:
        status = {"offsite_delivery_succeeded": True, "artifact_path": "already/sent.gpg"}
        with mock.patch.object(offsite_backup, "send_gmail") as sender:
            result = offsite_backup.deliver_with_retries(
                status,
                {"GMAIL_ADDRESS": "a@example.com", "GMAIL_APP_PASSWORD": "pw"},
                sleep_between_retries=False,
            )
        sender.assert_not_called()
        self.assertIs(result, status)


if __name__ == "__main__":
    unittest.main()
