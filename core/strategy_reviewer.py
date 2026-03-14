#!/usr/bin/env python3
"""
Echo Strategy Reviewer — weekly pattern analysis.
Reads event ledger, identifies what's working and what's not,
updates the Notion Strategy page with findings.
Runs weekly on Sunday at 6am.
"""
import json, sys, urllib.request
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import Counter

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/strategy_reviewer.log"
STRATEGY_PAGE_ID = "32319208c07d813f8d07f56207d66d2c"

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

def analyze_ledger():
    """Read event ledger and identify patterns."""
    import sqlite3
    db = BASE / "memory/echo_events.db"
    con = sqlite3.connect(db)

    # Last 7 days
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()

    # Total events this week
    total = con.execute(
        "SELECT COUNT(*) FROM events WHERE ts > ?", (week_ago,)
    ).fetchone()[0]

    # By type
    by_type = dict(con.execute(
        "SELECT event_type, COUNT(*) FROM events WHERE ts > ? GROUP BY event_type",
        (week_ago,)
    ).fetchall())

    # Win/loss ratio
    wins = con.execute(
        "SELECT COUNT(*) FROM events WHERE outcome_score > 0 AND ts > ?", (week_ago,)
    ).fetchone()[0]
    losses = con.execute(
        "SELECT COUNT(*) FROM events WHERE outcome_score < 0 AND ts > ?", (week_ago,)
    ).fetchone()[0]

    # Most common sources
    sources = con.execute(
        "SELECT source, COUNT(*) as n FROM events WHERE ts > ? GROUP BY source ORDER BY n DESC LIMIT 10",
        (week_ago,)
    ).fetchall()

    # Most common failing actions
    failures = con.execute(
        "SELECT summary, COUNT(*) as n FROM events WHERE outcome_score < 0 AND ts > ? GROUP BY summary ORDER BY n DESC LIMIT 5",
        (week_ago,)
    ).fetchall()

    # Most common successful actions
    successes = con.execute(
        "SELECT summary, COUNT(*) as n FROM events WHERE outcome_score > 0 AND ts > ? GROUP BY summary ORDER BY n DESC LIMIT 5",
        (week_ago,)
    ).fetchall()

    # Income events
    income = con.execute(
        "SELECT summary FROM events WHERE event_type='income' AND ts > ? ORDER BY ts DESC LIMIT 5",
        (week_ago,)
    ).fetchall()

    con.close()

    return {
        "total": total,
        "by_type": by_type,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / max(wins + losses, 1) * 100),
        "sources": sources,
        "failures": failures,
        "successes": successes,
        "income": income,
    }

def build_strategy_content(data):
    """Build strategy analysis text from ledger data."""
    today = datetime.now().strftime("%Y-%m-%d")
    win_rate = data["win_rate"]

    # What's working
    working = []
    for source, count in data["sources"][:5]:
        working.append(f"{source} ({count} events)")

    # What's failing
    failing = []
    for summary, count in data["failures"][:3]:
        failing.append(f"{summary[:80]} (failed {count}x)")

    # What's succeeding
    succeeding = []
    for summary, count in data["successes"][:3]:
        succeeding.append(f"{summary[:80]} (succeeded {count}x)")

    # Income signals
    income_notes = []
    for row in data["income"][:3]:
        income_notes.append(row[0][:100])

    working_text = "\n".join(f"- {w}" for w in working) or "No data yet"
    failing_text = "\n".join(f"- {f}" for f in failing) or "No failures this week"
    succeeding_text = "\n".join(f"- {s}" for s in succeeding) or "No data yet"
    income_text = "\n".join(f"- {i}" for i in income_notes) or "No income events this week"

    return {
        "working": f"Win rate: {win_rate}%\nTop active sources:\n{working_text}\n\nTop successes:\n{succeeding_text}",
        "not_working": failing_text,
        "income": income_text,
        "stats": f"Total events: {data['total']} | Wins: {data['wins']} | Losses: {data['losses']} | Win rate: {win_rate}%\nBy type: {data['by_type']}",
        "date": today,
    }

def update_notion_strategy(content):
    """Create a weekly strategy review page under Echo Dashboard."""
    import urllib.request, json as _json
    from pathlib import Path as _Path

    cfg = {}
    try:
        for line in (_Path.home() / ".config/echo/golem.env").read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    except Exception:
        pass

    token = cfg.get("NOTION_TOKEN")
    if not token:
        log("no token")
        return False

    today = content["date"]
    title = f"Weekly Strategy — {today}"
    body = f"""Stats: {content['stats']}

WORKING:
{content['working']}

NOT WORKING:
{content['not_working']}

INCOME:
{content['income']}"""

    payload = _json.dumps({
        "parent": {"page_id": "32219208c07d80798b88dd450b8c60fa"},
        "icon": {"emoji": "📊"},
        "properties": {
            "title": [{"type": "text", "text": {"content": title}}]
        },
        "children": [
            {"object": "block", "type": "paragraph",
             "paragraph": {"rich_text": [{"type": "text", "text": {"content": body[:2000]}}]}}
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
            result = _json.loads(r.read())
            log(f"weekly strategy page created: {title}")
            return True
    except Exception as e:
        log(f"notion write failed: {e}")
        return False

def _old_update_notion_strategy_unused(content):
    today = content["date"]
    new_entry = f"""### {today} — Weekly Pattern Analysis

**Stats:** {content['stats']}

**What's working:**
{content['working']}

**What's not working:**
{content['not_working']}

**Income signals:**
{content['income']}

---"""

    # Fetch current page content first
    req = urllib.request.Request(
        f"https://api.notion.com/v1/blocks/{STRATEGY_PAGE_ID}/children?page_size=100",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            pass  # just verify page exists
    except Exception as e:
        log(f"page fetch error: {e}")
        return False

    full_text = f"""--- {today} Weekly Review ---
Stats: {content['stats']}

WORKING:
{content['working']}

NOT WORKING:
{content['not_working']}

INCOME:
{content['income']}
"""
    payload = json.dumps({
        "children": [
            {"object": "block", "type": "paragraph",
             "paragraph": {"rich_text": [{"type": "text", "text": {"content": full_text[:2000]}}]}},
        ]
    }).encode()

    req = urllib.request.Request(
        f"https://api.notion.com/v1/blocks/{STRATEGY_PAGE_ID}/children",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        log(f"Strategy page updated for {today}")
        return True

def run():
    log("strategy_reviewer started")
    data = analyze_ledger()
    log(f"ledger analyzed: {data['total']} events, {data['win_rate']}% win rate")
    content = build_strategy_content(data)
    update_notion_strategy(content)

    # Log to event ledger
    try:
        sys.path.insert(0, str(BASE))
        from core.event_ledger import log_event
        log_event("knowledge", "strategy_reviewer",
            f"weekly strategy review: {data['total']} events, {data['win_rate']}% win rate",
            score=1.0)
    except Exception:
        pass

    # Rebalance standing task weights based on income progress
    try:
        import json as _json
        from pathlib import Path as _Path
        _sf = _Path("/home/andrew/Echo/memory/standing_tasks.json")
        _data = _json.loads(_sf.read_text())
        _today = datetime.now().strftime("%Y-%m-%d")

        # If no income yet — boost income-critical tasks
        if data["wins"] > 0 and data["income"] == []:
            for _t in _data["tasks"]:
                if _t["id"] in ["golem_status", "income_knowledge", "world_context"]:
                    _t["weight"] = min(2.0, _t["weight"] + 0.2)
                    log(f"rebalanced {_t['id']} weight → {_t['weight']:.2f} (no income yet)")

        _data["last_updated"] = _today
        _sf.write_text(_json.dumps(_data, indent=2))
        log("standing tasks rebalanced")
    except Exception as e:
        log(f"rebalance failed: {e}")

    log("strategy_reviewer done")

if __name__ == "__main__":
    run()
