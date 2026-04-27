#!/usr/bin/env python3
"""core/income_task_injector.py — injects income-related tasks into standing_tasks.json."""
import json
from datetime import datetime
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
TASKS_FILE = BASE / "memory/standing_tasks.json"
LOG = BASE / "logs/income_task_injector.log"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def load_tasks():
    if TASKS_FILE.exists():
        try:
            return json.loads(TASKS_FILE.read_text())
        except Exception:
            pass
    return {"tasks": []}


def save_tasks(tasks):
    tmp = TASKS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(tasks, indent=2, default=str))
    tmp.rename(TASKS_FILE)


def inject_task(title: str, category: str = "income", priority: int = 2):
    data = load_tasks()
    existing = [t.get("title", "") for t in data.get("tasks", [])]
    if title in existing:
        log(f"task already exists: {title[:50]}")
        return False
    data.setdefault("tasks", []).append({
        "title": title,
        "category": category,
        "priority": priority,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    })
    save_tasks(data)
    log(f"injected: {title[:50]}")
    return True


def run():
    log("income_task_injector starting")

    # Check for high-score leads needing outreach
    leads_file = BASE / "memory/demand_leads.json"
    if leads_file.exists():
        try:
            leads = json.loads(leads_file.read_text())
            hot = [l for l in leads if l.get("score", 0) >= 8 and not l.get("dm_sent")]
            if hot:
                inject_task(
                    f"Send outreach DM to {len(hot)} high-score Fiverr leads",
                    category="income",
                    priority=1,
                )
        except Exception as e:
            log(f"leads check error: {e}")

    # Check for unread content drafts
    drafts_dir = BASE / "content/drafts"
    if drafts_dir.exists():
        drafts = list(drafts_dir.glob("*.md"))
        if drafts:
            inject_task(
                f"Review and publish {len(drafts)} content draft(s) to dev.to",
                category="content",
                priority=2,
            )

    log("income_task_injector done")

    try:
        from core.event_ledger import log_event
        log_event("system", "income_task_injector", "tasks checked", score=1.0)
    except Exception:
        pass


if __name__ == "__main__":
    run()
