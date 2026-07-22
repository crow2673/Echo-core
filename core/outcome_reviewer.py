#!/usr/bin/env python3
"""core/outcome_reviewer.py — post-trade belief updates.
Reviews trade outcomes and updates belief scores in the event ledger.
Runs every 30 minutes via echo-outcome-reviewer.timer.
"""
import json
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LOG = BASE / "logs/outcome_reviewer.log"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def load_config():
    env = {}
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def get_devto_views():
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://dev.to/api/articles/me?per_page=20",
            headers={"User-Agent": "Echo/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            articles = json.loads(r.read())
        return sum(a.get("page_views_count", 0) for a in articles)
    except Exception:
        return 0


def get_ledger_stats():
    try:
        import sqlite3
        db = BASE / "memory/echo_events.db"
        if not db.exists():
            return {}
        conn = sqlite3.connect(db)
        total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        wins = conn.execute("SELECT COUNT(*) FROM events WHERE outcome_score > 0").fetchone()[0]
        losses = conn.execute("SELECT COUNT(*) FROM events WHERE outcome_score < 0").fetchone()[0]
        neutral = total - wins - losses
        articles = conn.execute(
            "SELECT COUNT(*) FROM events WHERE source='article_pipeline' AND outcome_score > 0"
        ).fetchone()[0]
        today = date.today().strftime("%Y-%m-%d")
        today_events = conn.execute(
            f"SELECT COUNT(*) FROM events WHERE ts LIKE '{today}%'"
        ).fetchone()[0]
        conn.close()
        return {
            "total": total,
            "scored": wins + losses,
            "wins": wins,
            "losses": losses,
            "neutral": neutral,
            "articles": articles,
            "today": today_events,
        }
    except Exception:
        return {}


def run():
    log("outcome_reviewer starting")
    env = load_config()
    token = env.get("NOTION_TOKEN", "")
    if not token:
        log("no NOTION_TOKEN — skipping Notion update")

    views = get_devto_views()
    stats = get_ledger_stats()
    wins = stats.get("wins", 0)
    total = stats.get("total", 0)
    scored = stats.get("scored", 0)
    losses = stats.get("losses", 0)
    neutral = stats.get("neutral", 0)
    win_rate = round(wins / scored * 100) if scored else 0

    now = datetime.now()
    summary = (
        f"Views: {views} | Articles: {stats.get('articles', 0)} | "
        f"Events: {total} | Scored: {scored} | Win rate: {win_rate}% | "
        f"Wins: {wins} | Losses: {losses} | Neutral/unscored: {neutral}"
    )
    log(f"outcomes: {summary}")

    if token:
        try:
            from core.notion_bridge import log_event_to_notion
            log_event_to_notion("outcome_review", "outcome_reviewer", summary, score=win_rate / 100)
        except Exception as e:
            log(f"notion log failed: {e}")

    try:
        from core.event_ledger import log_event
        log_event("system", "outcome_reviewer", summary, score=win_rate / 100)
    except Exception:
        pass

    log("outcome_reviewer done")


if __name__ == "__main__":
    run()
