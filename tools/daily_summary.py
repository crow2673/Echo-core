#!/usr/bin/env python3
"""
tools/daily_summary.py — Echo's 8pm daily activity digest
Summarises what happened today: trades, events, actions, leads, errors.
Sends to Telegram via notifier. Runs via echo-daily-summary.timer.
"""
import json
import subprocess
from datetime import datetime, date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(BASE))


def count_today_journal(service):
    """Count journal lines from a service today."""
    try:
        result = subprocess.run(
            ["journalctl", "--user", "-u", service, "--since", "today", "--no-pager", "-q"],
            capture_output=True, text=True, timeout=10
        )
        return len([l for l in result.stdout.splitlines() if l.strip()])
    except Exception:
        return 0


def get_trade_summary():
    try:
        trade_log = BASE / "memory/trade_log.json"
        if not trade_log.exists():
            return "no trade log"
        trades = json.loads(trade_log.read_text())
        open_pos = [s for s, t in trades.items() if isinstance(t, dict) and not t.get("closed_at")]
        closed_today = [
            s for s, t in trades.items()
            if isinstance(t, dict) and t.get("closed_at", "").startswith(date.today().isoformat())
        ]
        return f"{len(open_pos)} open, {len(closed_today)} closed today"
    except Exception as e:
        return f"error: {e}"


def get_crypto_summary():
    try:
        crypto_log = BASE / "memory/crypto_trade_log.json"
        if not crypto_log.exists():
            return "no crypto log"
        trades = json.loads(crypto_log.read_text())
        open_pos = [s for s, t in trades.items() if isinstance(t, dict) and not t.get("closed_at")]
        return f"{len(open_pos)} open crypto positions"
    except Exception:
        return "no data"


def get_event_summary():
    try:
        from core.event_ledger import query_summary
        s = query_summary()
        total = s.get("total", 0)
        wins = s.get("wins", 0)
        win_rate = round(wins / total * 100) if total else 0
        return f"{total} events, {win_rate}% win rate"
    except Exception:
        return "event ledger unavailable"


def get_new_leads():
    try:
        leads_file = BASE / "memory/demand_leads.json"
        if not leads_file.exists():
            return "0 leads"
        leads = json.loads(leads_file.read_text())
        today = date.today().isoformat()
        new_today = [l for l in leads if l.get("found_at", "").startswith(today)]
        top = [l for l in new_today if l.get("score", 0) >= 7]
        return f"{len(new_today)} new leads today ({len(top)} score≥7)"
    except Exception:
        return "leads unavailable"


def get_failed_services():
    try:
        result = subprocess.run(
            ["systemctl", "--user", "list-units", "--type=service", "--state=failed", "--no-pager"],
            capture_output=True, text=True, timeout=10
        )
        failed = [l.strip().split()[1] for l in result.stdout.splitlines() if "echo-" in l.strip() and l.strip() and not l.strip().startswith("UNIT")]
        return f"{len(failed)} failed: {', '.join(failed[:4])}" if failed else "all services ok"
    except Exception:
        return "unknown"


def run():
    now = datetime.now()
    lines = [
        f"📊 Echo Daily Summary — {now.strftime('%A %b %d, %Y')}",
        "",
        f"📈 Stocks: {get_trade_summary()}",
        f"₿  Crypto: {get_crypto_summary()}",
        f"🧠 Events: {get_event_summary()}",
        f"🎯 Leads: {get_new_leads()}",
        f"⚙️  Services: {get_failed_services()}",
    ]

    msg = "\n".join(lines)
    print(msg, flush=True)

    try:
        from core.notifier import notify
        notify("Echo Daily Summary", msg, urgent=False)
    except Exception as e:
        print(f"notify failed: {e}", flush=True)

    try:
        from core.event_ledger import log_event
        log_event("system", "daily_summary", "daily summary sent", score=1.0)
    except Exception:
        pass


if __name__ == "__main__":
    run()
