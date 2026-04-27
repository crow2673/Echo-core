#!/usr/bin/env python3
"""core/initiative_engine.py — proactive trigger watcher.
Reads demand_leads.json and fires alerts for unactioned high-score leads.
Runs every 15 minutes via echo-initiative.timer.
"""
import json
from datetime import datetime, date
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LEADS_FILE = BASE / "memory/demand_leads.json"
LOG = BASE / "logs/initiative.log"
ALERT_THRESHOLD = 8
MAX_ALERTS_PER_RUN = 3


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def run():
    log("initiative_engine starting")

    if not LEADS_FILE.exists():
        log("no leads file — nothing to do")
        return

    try:
        leads = json.loads(LEADS_FILE.read_text())
    except Exception as e:
        log(f"leads load error: {e}")
        return

    today = date.today().isoformat()
    hot = [
        l for l in leads
        if l.get("score", 0) >= ALERT_THRESHOLD
        and not l.get("alerted", False)
        and l.get("found_at", "").startswith(today)
    ]

    if not hot:
        log(f"no new hot leads today (threshold={ALERT_THRESHOLD})")
        return

    hot.sort(key=lambda l: l.get("score", 0), reverse=True)
    to_alert = hot[:MAX_ALERTS_PER_RUN]

    try:
        from core.notifier import notify
        for lead in to_alert:
            msg = f"Score {lead['score']}/10 [{lead['subreddit']}]: {lead['title'][:80]}\n{lead.get('url', '')}"
            notify("Fiverr Lead", msg, urgent=True)
            lead["alerted"] = True
            log(f"alerted: {lead['title'][:60]}")
    except Exception as e:
        log(f"notify error: {e}")
        return

    # Save updated alerted flags
    tmp = LEADS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(leads, indent=2, default=str))
    tmp.rename(LEADS_FILE)

    log(f"initiative_engine done — {len(to_alert)} alerts fired")

    try:
        from core.event_ledger import log_event
        log_event("income", "initiative_engine", f"{len(to_alert)} leads alerted", score=1.0)
    except Exception:
        pass


if __name__ == "__main__":
    run()
