#!/usr/bin/env python3
"""Lightweight event ledger — logs Echo actions/reasoning to SQLite."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / "Echo/memory/echo_events.db"


def _conn():
    db = sqlite3.connect(str(DB_PATH), timeout=10)
    db.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_type TEXT,
            source TEXT,
            summary TEXT,
            score REAL,
            data TEXT
        )
    """)
    db.commit()
    return db


def log_event(event_type: str, source: str, summary: str, score: float = 0.0, data=None):
    try:
        db = _conn()
        db.execute(
            "INSERT INTO events (ts, event_type, source, summary, score, data) VALUES (?,?,?,?,?,?)",
            (datetime.now().isoformat(), event_type, source, summary[:500], score,
             json.dumps(data) if data is not None else None)
        )
        db.commit()
        db.close()
    except Exception as e:
        print(f"[event_ledger] log_event failed: {e}")


def query_recent(limit: int = 20, event_type: str = None, source: str = None) -> list:
    try:
        db = _conn()
        where, params = [], []
        if event_type:
            where.append("event_type = ?"); params.append(event_type)
        if source:
            where.append("source = ?"); params.append(source)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = db.execute(
            f"SELECT ts, event_type, source, summary, score FROM events {clause} ORDER BY id DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        db.close()
        return [{"ts": r[0], "event_type": r[1], "source": r[2], "summary": r[3], "score": r[4]} for r in rows]
    except Exception as e:
        print(f"[event_ledger] query_recent failed: {e}")
        return []


def query_summary() -> dict:
    try:
        db = _conn()
        total = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        by_type = db.execute(
            "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
        ).fetchall()
        avg_score = db.execute("SELECT AVG(score) FROM events WHERE score != 0").fetchone()[0] or 0.0
        db.close()
        return {"total": total, "by_type": dict(by_type), "avg_score": round(avg_score, 3)}
    except Exception as e:
        print(f"[event_ledger] query_summary failed: {e}")
        return {"total": 0, "by_type": {}, "avg_score": 0.0}
