#!/usr/bin/env python3
"""
Echo Outcomes Updater — creates a daily outcomes page in Notion.
Uses the same page-creation pattern as notion_briefing.py which works.
"""
import json
import urllib.request
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LOG = BASE / "logs/outcomes_updater.log"
DASHBOARD_PAGE_ID = "32219208c07d80798b88dd450b8c60fa"


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
        req = urllib.request.Request(
            "https://dev.to/api/articles/me?per_page=20",
            headers={"User-Agent": "Echo/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            articles = json.loads(r.read())
        return sum(a.get("page_views_count", 0) for a in articles), len(articles)
    except Exception:
        return 0, 0


def get_ledger_stats():
    try:
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
        today = datetime.now().strftime("%Y-%m-%d")
        today_events = conn.execute(
            f"SELECT COUNT(*) FROM events WHERE ts LIKE '{today}%'"
        ).fetchone()[0]
        conn.close()
        scored = wins + losses
        win_rate = round(wins / scored * 100) if scored else 0
        return {
            "total": total,
            "scored": scored,
            "wins": wins,
            "losses": losses,
            "neutral": neutral,
            "articles": articles,
            "today": today_events,
            "win_rate": win_rate,
        }
    except Exception:
        return {}


def run():
    log("outcomes_updater started")
    cfg = load_config()
    token = cfg.get("NOTION_TOKEN", "")
    if not token:
        log("no NOTION_TOKEN")
        return

    views, article_count = get_devto_views()
    stats = get_ledger_stats()
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    scored = stats.get("scored", 0)
    neutral = stats.get("neutral", 0)
    win_rate = stats.get("win_rate", 0)
    total = stats.get("total", 0)

    # Alpaca portfolio
    portfolio_str = "unknown"
    try:
        env = cfg
        key = env.get("ALPACA_API_KEY", "")
        secret = env.get("ALPACA_SECRET_KEY", "")
        base_url = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        if key and secret:
            req = urllib.request.Request(
                f"{base_url}/v2/account",
                headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                acct = json.loads(r.read())
            pv = float(acct.get("portfolio_value", 0))
            earned = float(acct.get("equity", 0)) - float(acct.get("last_equity", 0))
            portfolio_str = f"${pv:,.0f} (day: ${earned:+.0f})"
    except Exception:
        pass

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_str = datetime.now().strftime("%Y-%m-%d")

    summary = (
        f"Views: {views} | Articles: {article_count} | Echo wrote: {stats.get('articles', 0)} | "
        f"Events: {total} | Scored: {scored} | Win rate: {win_rate}% | "
        f"Wins: {wins} | Losses: {losses} | Neutral/unscored: {neutral} | "
        f"Golem: Down | Earned: $0.00"
    )

    try:
        from core.notion_bridge import log_event_to_notion
        log_event_to_notion("outcome_update", "outcomes_updater", summary, score=win_rate / 100)
        log("Notion event logged")
    except Exception as e:
        log(f"Notion log failed: {e}")

    log(f"outcomes_updater done: {summary}")


if __name__ == "__main__":
    run()
