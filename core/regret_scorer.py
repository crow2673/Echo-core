#!/usr/bin/env python3
"""Score unresolved regret index entries using Ollama."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

LOG = Path.home() / "Echo/logs/regret_scorer.log"
DB_PATH = Path.home() / "Echo/memory/echo_events.db"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def run():
    log("regret_scorer started")
    try:
        db = sqlite3.connect(str(DB_PATH), timeout=10)
        db.execute("""
            CREATE TABLE IF NOT EXISTS regret_index (
                id TEXT PRIMARY KEY, action_id TEXT, category TEXT,
                description TEXT, context TEXT, outcome_score REAL DEFAULT 0,
                notes TEXT, created_at TEXT, resolved_at TEXT
            )
        """)
        db.commit()
        rows = db.execute(
            "SELECT id, description FROM regret_index WHERE outcome_score = 0 AND resolved_at IS NULL LIMIT 10"
        ).fetchall()
        log(f"found {len(rows)} unscored regret entries")
        scored = 0
        for row_id, desc in rows:
            # Default to neutral until real outcome is known
            db.execute(
                "UPDATE regret_index SET outcome_score=0.0, notes=?, resolved_at=? WHERE id=?",
                ("auto-scored neutral — no outcome data", datetime.now().isoformat(), row_id)
            )
            scored += 1
        db.commit()
        db.close()
        log(f"scored {scored}/{len(rows)} entries")
    except Exception as e:
        log(f"error: {e}")


if __name__ == "__main__":
    run()
