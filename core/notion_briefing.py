#!/usr/bin/env python3
"""
Echo Notion Daily Briefing
Writes a daily summary page to the Echo Dashboard in Notion.
Runs daily at 8am after the voice briefing.
"""
import json, urllib.request, sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]

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

def api_call(payload, token):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def block(type_, content):
    if type_ == "heading_2":
        return {"object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": content[:2000]}}]}}
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": content[:2000]}}]}}

def run():
    config = load_config()
    token = config.get("NOTION_TOKEN")
    parent_id = "32219208c07d80798b88dd450b8c60fa"

    if not token:
        print("ERROR: no NOTION_TOKEN")
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Collect data
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path.home()))
        system_stats = f"CPU: {cpu}% | RAM: {ram.percent}% used ({ram.used//1024**3}GB/{ram.total//1024**3}GB) | Disk: {disk.percent}%"
    except Exception:
        system_stats = "system stats unavailable"

    try:
        sys.path.insert(0, str(BASE))
        from core.event_ledger import query_summary
        ls = query_summary()
        ledger_stats = f"Total events: {ls['total_events']} | Wins: {ls['wins']} | Losses: {ls['losses']}\nBy type: {ls['by_type']}"
        recent = "\n".join([f"• [{r['event_type']}] {r['source']}: {r['summary'][:80]}" for r in ls['recent'][:5]])
    except Exception as e:
        ledger_stats = f"unavailable: {e}"
        recent = ""

    try:
        income_md = (BASE / "memory/income_knowledge.md").read_text()[:800]
    except Exception:
        income_md = "unavailable"

    try:
        todo_lines = [l for l in (BASE / "TODO.md").read_text().splitlines() if "[ ]" in l]
        todo_text = "\n".join(todo_lines[:8])
    except Exception:
        todo_text = "unavailable"

    try:
        healthcheck = __import__("subprocess").run(
            ["bash", str(BASE / "echo_healthcheck.sh")],
            capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except Exception:
        healthcheck = "unavailable"

    # Build Notion page
    title = f"Echo Daily Briefing — {today}"
    blocks = [
        block("paragraph", f"Generated: {now_str} | Echo autonomous AI system — Mena, Arkansas"),
        block("heading_2", "🖥️ System Health"),
        block("paragraph", system_stats),
        block("paragraph", healthcheck),
        block("heading_2", "📊 Event Ledger"),
        block("paragraph", ledger_stats),
        block("paragraph", recent),
        block("heading_2", "💰 Income Status"),
        block("paragraph", income_md),
        block("heading_2", "📋 Open Tasks"),
        block("paragraph", todo_text),
    ]

    payload = {
        "parent": {"page_id": parent_id},
        "icon": {"emoji": "📋"},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
        "children": blocks
    }

    result = api_call(payload, token)
    print(f"[notion_briefing] Created: {title}")
    print(f"[notion_briefing] URL: {result.get('url', 'unknown')}")

    # Log to event ledger
    try:
        from core.event_ledger import log_event
        log_event("knowledge", "notion_briefing",
            f"Daily briefing page created: {title}", score=1.0)
    except Exception:
        pass

    return True

if __name__ == "__main__":
    run()
