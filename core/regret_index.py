#!/usr/bin/env python3
"""Regret index — tracks action outcomes and flags bad categories."""
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / "Echo/memory/echo_events.db"
FLAGS_FILE = Path.home() / "Echo/memory/regret_patterns.json"


def _conn():
    db = sqlite3.connect(str(DB_PATH), timeout=10)
    db.execute("""
        CREATE TABLE IF NOT EXISTS regret_index (
            id TEXT PRIMARY KEY,
            action_id TEXT,
            category TEXT,
            description TEXT,
            context TEXT,
            outcome_score REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT,
            resolved_at TEXT
        )
    """)
    db.commit()
    return db


def log_action(action_id: str, category: str, description: str, context: str = "") -> str:
    entry_id = str(uuid.uuid4())[:8]
    try:
        db = _conn()
        db.execute(
            "INSERT INTO regret_index (id, action_id, category, description, context, created_at) VALUES (?,?,?,?,?,?)",
            (entry_id, action_id, category, description[:500], context, datetime.now().isoformat())
        )
        db.commit()
        db.close()
    except Exception as e:
        print(f"[regret_index] log_action failed: {e}")
    return entry_id


def update_outcome(entry_id: str, score: float, notes: str = ""):
    try:
        db = _conn()
        db.execute(
            "UPDATE regret_index SET outcome_score=?, notes=?, resolved_at=? WHERE id=?",
            (score, notes[:300], datetime.now().isoformat(), entry_id)
        )
        db.commit()
        db.close()
        _recompute_flags()
    except Exception as e:
        print(f"[regret_index] update_outcome failed: {e}")


def get_flags() -> list:
    """Return list of (type, value) tuples for flagged categories/actions."""
    try:
        if FLAGS_FILE.exists():
            data = json.loads(FLAGS_FILE.read_text())
            return [(f["type"], f["value"]) for f in data.get("flags", [])]
    except Exception:
        pass
    return []


def _recompute_flags():
    """Flag any category averaging <= -0.7 over last 20 scored actions."""
    try:
        db = _conn()
        rows = db.execute("""
            SELECT category, AVG(outcome_score), COUNT(*)
            FROM regret_index
            WHERE outcome_score != 0
            GROUP BY category
            HAVING COUNT(*) >= 5
        """).fetchall()
        db.close()

        flags = []
        for category, avg, count in rows:
            if avg <= -0.7:
                flags.append({"type": "category", "value": category, "avg": avg, "count": count})

        FLAGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        FLAGS_FILE.write_text(json.dumps({"flags": flags, "updated_at": datetime.now().isoformat()}, indent=2))
    except Exception as e:
        print(f"[regret_index] _recompute_flags failed: {e}")
