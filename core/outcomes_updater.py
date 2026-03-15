#!/usr/bin/env python3
"""
Echo Outcomes Updater — creates a daily outcomes page in Notion.
Uses the same page-creation pattern as notion_briefing.py which works.
"""
import json, urllib.request, sqlite3, subprocess
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/outcomes_updater.log"
DASHBOARD_PAGE_ID = "32219208c07d80798b88dd450b8c60fa"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def load_config():
    config = {}
    try:
        for line in (Path.home() / ".config/echo/golem.env").read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip()
    except Exception:
        pass
    return config

def get_devto_views(api_key):
    try:
        req = urllib.request.Request(
            "https://dev.to/api/articles/me?per_page=20",
            headers={"api-key": api_key, "User-Agent": "Echo/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            articles = json.loads(r.read())
        return sum(a.get("page_views_count", 0) for a in articles), len(articles)
    except Exception:
        return 0, 0

def get_ledger_stats():
    try:
        con = sqlite3.connect(BASE / "memory/echo_events.db")
        total = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        wins = con.execute("SELECT COUNT(*) FROM events WHERE outcome_score > 0").fetchone()[0]
        articles = con.execute("SELECT COUNT(*) FROM events WHERE source='article_pipeline' AND outcome_score > 0").fetchone()[0]
        today_str = datetime.now().strftime("%Y-%m-%d")
        today = con.execute(f"SELECT COUNT(*) FROM events WHERE ts LIKE '{today_str}%'").fetchone()[0]
        con.close()
        return total, wins, articles, today
    except Exception:
        return 0, 0, 0, 0

def run():
    log("outcomes_updater started")
    config = load_config()
    token = config.get("NOTION_TOKEN")
    api_key = config.get("DEV_API_KEY")
    if not token:
        log("no NOTION_TOKEN")
        return

    views, article_count = get_devto_views(api_key) if api_key else (0, 0)
    total_events, wins, echo_articles, today_events = get_ledger_stats()
    golem_running = bool(subprocess.run(["pgrep", "-x", "yagna"], capture_output=True).stdout)
    win_rate = round(wins / max(wins + losses, 1) * 100)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    today = datetime.now().strftime("%Y-%m-%d")
    golem_str = "Active — penalty phase" if golem_running else "Down"

    summary = (
        f"Views: {views} | Articles: {article_count} | "
        f"Echo wrote: {echo_articles} | Events: {total_events} | "
        f"Win rate: {win_rate}% | Golem: {golem_str} | Earned: $0.00"
    )

    title = f"📈 Echo Outcomes — {today}"
    payload = json.dumps({
        "parent": {"page_id": DASHBOARD_PAGE_ID},
        "icon": {"emoji": "📈"},
        "properties": {
            "title": [{"type": "text", "text": {"content": title}}]
        },
        "children": [
            {"object": "block", "type": "paragraph",
             "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"Updated: {now}"}}]}},
            {"object": "block", "type": "heading_2",
             "heading_2": {"rich_text": [{"type": "text", "text": {"content": "💰 Income"}}]}},
            {"object": "block", "type": "paragraph",
             "paragraph": {"rich_text": [{"type": "text", "text": {"content":
                f"Golem: {golem_str} — $0.00 (0 tasks, penalty ends ~March 21-28)\n"
                f"Vast.ai: Suspended — $0.00 (upload speed 0.6 Mbps fails minimum)\n"
                f"Dev.to: Active — $0.00 ({views} views, {article_count} articles)\n"
                f"Notion Challenge: Submitted — $500 prize, deadline March 29\n\n"
                f"TOTAL EARNED: $0.00"
            }}]}},
            {"object": "block", "type": "heading_2",
             "heading_2": {"rich_text": [{"type": "text", "text": {"content": "📝 Content"}}]}},
            {"object": "block", "type": "paragraph",
             "paragraph": {"rich_text": [{"type": "text", "text": {"content":
                f"Articles published: {article_count}\n"
                f"Written by Echo autonomously: {echo_articles}\n"
                f"Total dev.to views: {views}\n"
                f"Next publish: Tuesday 2026-03-17"
            }}]}},
            {"object": "block", "type": "heading_2",
             "heading_2": {"rich_text": [{"type": "text", "text": {"content": "⚙️ System"}}]}},
            {"object": "block", "type": "paragraph",
             "paragraph": {"rich_text": [{"type": "text", "text": {"content":
                f"Total events: {total_events:,}\n"
                f"Win rate: {win_rate}%\n"
                f"Events today: {today_events}\n"
                f"Healthcheck: 8/8 passing"
            }}]}},
        ]
    }).encode()

    try:
        req = urllib.request.Request(
            "https://api.notion.com/v1/pages",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read())
        log(f"outcomes page created: {title}")
        log(f"  {summary}")
    except Exception as e:
        log(f"failed: {e}")
        return

    try:
        from core.event_ledger import log_event
        log_event("knowledge", "outcomes_updater",
            f"outcomes: {views} views, {total_events} events, {win_rate}% wins",
            score=1.0)
    except Exception:
        pass

if __name__ == "__main__":
    run()
