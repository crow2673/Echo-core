from __future__ import annotations

from pathlib import Path

from core import interaction_ledger


def _isolated_ledger(tmp_path, monkeypatch, configured_chat_id: str | None):
    root = tmp_path / "echo"
    logs = root / "logs"
    memory = root / "memory"
    logs.mkdir(parents=True)
    memory.mkdir()
    chat_file = tmp_path / "telegram_chat_id"
    if configured_chat_id is not None:
        chat_file.write_text(configured_chat_id)
    monkeypatch.setattr(interaction_ledger, "BASE", root)
    monkeypatch.setattr(interaction_ledger, "LEDGER", memory / "interaction_ledger.jsonl")
    monkeypatch.setattr(interaction_ledger, "TELEGRAM_CHAT_ID_FILE", chat_file)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    return logs, interaction_ledger.LEDGER


def test_backfill_uses_configured_chat_id(tmp_path, monkeypatch):
    logs, ledger = _isolated_ledger(tmp_path, monkeypatch, "424242")
    (logs / "telegram_intake.log").write_text(
        "2026-01-01 00:00:00 [telegram] from 424242: fixture hello\n"
    )

    assert interaction_ledger.backfill_from_telegram() == 1
    assert "fixture hello" in ledger.read_text()


def test_backfill_ignores_different_chat_id(tmp_path, monkeypatch):
    logs, ledger = _isolated_ledger(tmp_path, monkeypatch, "424242")
    (logs / "telegram_intake.log").write_text(
        "2026-01-01 00:00:00 [telegram] from 999999: wrong user\n"
    )

    assert interaction_ledger.backfill_from_telegram() == 0
    assert not ledger.exists()


def test_backfill_missing_chat_id_fails_closed(tmp_path, monkeypatch):
    logs, ledger = _isolated_ledger(tmp_path, monkeypatch, None)
    (logs / "telegram_intake.log").write_text(
        "2026-01-01 00:00:00 [telegram] from 424242: fixture hello\n"
    )

    assert interaction_ledger.backfill_from_telegram() == 0
    assert not ledger.exists()


def test_backfill_malformed_chat_id_cannot_change_regex(tmp_path, monkeypatch):
    logs, ledger = _isolated_ledger(tmp_path, monkeypatch, "424242.*")
    (logs / "telegram_intake.log").write_text(
        "2026-01-01 00:00:00 [telegram] from 424242999: should not match\n"
    )

    assert interaction_ledger.backfill_from_telegram() == 0
    assert not ledger.exists()


def test_existing_interaction_ledger_behavior_remains_intact(tmp_path, monkeypatch):
    _, ledger = _isolated_ledger(tmp_path, monkeypatch, "424242")

    turn = interaction_ledger.record("andrew", "that is wrong")

    assert turn["role"] == "andrew"
    assert turn["kind"] == "correction"
    assert interaction_ledger.last_andrew()["text"] == "that is wrong"
    assert "Andrew [correction]: that is wrong" in interaction_ledger.context_block(1)
    assert ledger.exists()
