#!/usr/bin/env python3
"""
Echo Notion Daily Briefing
Writes a daily summary page to the Echo Dashboard in Notion.
Runs daily at 8am after the voice briefing.
"""
import json
import urllib.request
from datetime import datetime
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
ECHO_DASHBOARD_PAGE_ID = "32219208c07d80798b88dd450b8c60fa"


def load_config():
    env = {}
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def api_call(token, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def block(text, btype="heading_2"):
    return {
        "object": "block",
        "type": btype,
        btype: {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def run():
    cfg = load_config()
    token = cfg.get("NOTION_TOKEN", "")
    if not token:
        print("ERROR: no NOTION_TOKEN")
        return

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%Y-%m-%d %H:%M")

    sections = []

    try:
        from core.self_awareness import build_self_awareness_block
        sections.append(f"System Status:\n{build_self_awareness_block()[:1500]}")
    except Exception:
        sections.append("System status unavailable")

    try:
        from core.trade_brain import get_market_regime, load_env
        env = load_env()
        regime = get_market_regime(env.get("ALPACA_API_KEY"), env.get("ALPACA_SECRET_KEY"))
        sections.append(f"Market: {regime}")
    except Exception:
        sections.append("Market regime unavailable")

    try:
        leads_file = BASE / "memory/demand_leads.json"
        if leads_file.exists():
            leads = json.loads(leads_file.read_text())
            top = [l for l in leads if l.get("score", 0) >= 7][:3]
            if top:
                lead_lines = [f"Score {l['score']}: {l['title'][:60]}" for l in top]
                sections.append("Top Leads:\n" + "\n".join(lead_lines))
    except Exception:
        pass

    children = [block(f"Echo Daily Briefing — {date_str}", "heading_1")]
    for s in sections:
        children.append(block(s, "paragraph"))

    try:
        api_call(token, {
            "parent": {"page_id": ECHO_DASHBOARD_PAGE_ID},
            "properties": {
                "title": {"title": [{"text": {"content": f"Echo Briefing {date_str}"}}]}
            },
            "children": children[:50],
        })
        print(f"[notion_briefing] page created: {date_str}")
    except Exception as e:
        print(f"[notion_briefing] failed: {e}")


if __name__ == "__main__":
    run()
