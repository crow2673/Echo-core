#!/usr/bin/env python3
"""
core/event_ledger.py
====================
Unified event ledger. Single SQLite source of truth.
All sources (self_act, auto_act, feedback_loop, regret_index) write here.
Echo can query across all event types in one call.

Usage:
    from core.event_ledger import log_event, query_recent

    log_event("reasoning", "self_act", "summarized system state", score=None)
    log_event("action", "auto_act", "restarted echo-core", score=1.0, tags="service")
    log_event("feedback", "feedback_loop", "suggested pricing change", score=None)
    log_event("income", "golem_monitor", "0 tasks, 2.85 GLM balance", score=0.0)

    rows = query_recent(limit=10, event_type="action")
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "memory" / "echo_events.db"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def log_event(
    event_type: str,
    source: str,
    summary: str,
    data: dict | str | None = None,
    score: float | None = None,
    tags: str | None = None,
    ts: str | None = None,
) -> int:
    """Append an event to the ledger. Returns new row id."""
    ts = ts or datetime.now().isoformat()
    data_str = json.dumps(data) if isinstance(data, dict) else (data or "")
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO events (ts, event_type, source, summary, data, outcome_score, tags) "
            "VALUES (?,?,?,?,?,?,?)",
            (ts, event_type, source, summary[:500], data_str, score, tags)
        )
        row_id = cur.lastrowid

    # Mirror to Notion asynchronously — never block the ledger
    try:
        from core.notion_bridge import log_event_to_notion, log_income_to_notion
        log_event_to_notion(event_type, source, summary, score)
        # Also log income events to Income Tracker database
        if event_type == "income":
            stream_map = {
                "golem": "Golem Network",
                "vast": "Vast.ai GPU",
                "devto": "Dev.to Content",
                "dev.to": "Dev.to Content",
                "income_researcher": "Income Research",
            }
            stream = next((v for k, v in stream_map.items() if k in source.lower()), source)
            status = "active" if (score or 0) > 0 else "pending"
            log_income_to_notion(stream, status, summary[:300])
    except Exception:
        pass

    return row_id


def query_recent(
    limit: int = 20,
    event_type: str | None = None,
    source: str | None = None,
    min_score: float | None = None,
) -> list[dict]:
    """Query recent events. Returns list of dicts."""
    sql = "SELECT * FROM events WHERE 1=1"
    params = []
    if event_type:
        sql += " AND event_type = ?"
        params.append(event_type)
    if source:
        sql += " AND source = ?"
        params.append(source)
    if min_score is not None:
        sql += " AND outcome_score >= ?"
        params.append(min_score)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def query_summary(days: int = 7) -> dict:
    """High level summary for Echo's reasoning."""
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        by_type = dict(conn.execute(
            "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
        ).fetchall())
        wins = conn.execute(
            "SELECT COUNT(*) FROM events WHERE outcome_score > 0"
        ).fetchone()[0]
        losses = conn.execute(
            "SELECT COUNT(*) FROM events WHERE outcome_score < 0"
        ).fetchone()[0]
        recent = conn.execute(
            "SELECT ts, event_type, source, summary, outcome_score "
            "FROM events ORDER BY id DESC LIMIT 5"
        ).fetchall()
    return {
        "total_events": total,
        "by_type": by_type,
        "wins": wins,
        "losses": losses,
        "recent": [dict(r) for r in recent]
    }


if __name__ == "__main__":
    print(json.dumps(query_summary(), indent=2))
