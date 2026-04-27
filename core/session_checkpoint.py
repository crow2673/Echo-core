#!/usr/bin/env python3
"""
session_checkpoint.py — Phase 3B
Automatically writes session_summary.json at the end of each session.
Reads: CHANGELOG, auto_act.log, trade_log, regret_patterns
Runs at 23:55 nightly via echo-session-checkpoint.timer
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SESSION_FILE = BASE / "memory/session_summary.json"
CHANGELOG = BASE / "CHANGELOG.md"
AUTO_ACT_LOG = BASE / "logs/auto_act.log"
TRADE_LOG = BASE / "memory/trade_log.json"
REGRET_PATTERNS = BASE / "memory/regret_patterns.json"


def log(msg):
    print(f"[checkpoint] {msg}", flush=True)


def get_focus_from_changelog():
    """Pull today's ## headers from CHANGELOG and join into a focus statement.
    Filters noise, deduplicates, caps at 4 items."""
    if not CHANGELOG.exists():
        return "Recent build work"
    today = datetime.now().strftime("%Y-%m-%d")
    lines = CHANGELOG.read_text().splitlines()
    headers = []
    in_today = False
    for line in lines:
        if today in line:
            in_today = True
        if in_today and line.startswith("## ") and today not in line:
            in_today = False
        if in_today and line.startswith("- "):
            item = line[2:].strip()
            if item and item not in headers and "auto" not in item.lower():
                headers.append(item)
    if not headers:
        return "Build session"
    return "; ".join(headers[:4])


def get_trade_summary():
    """Quick trade summary."""
    try:
        if not TRADE_LOG.exists():
            return "No trade log"
        trades = json.loads(TRADE_LOG.read_text())
        open_count = sum(1 for t in trades.values() if isinstance(t, dict) and not t.get("closed_at"))
        return f"{open_count} positions open"
    except Exception as e:
        return f"Trade status unknown"


def get_regret_health():
    """Check regret index health."""
    try:
        sys_path = str(BASE)
        import sys
        if sys_path not in sys.path:
            sys.path.insert(0, sys_path)
        from core.regret_index import get_flags
        flags = get_flags()
        if flags:
            flagged = [f[1] for f in flags]
            return f"flagged: {', '.join(flagged[:3])}"
        return "clean"
    except Exception as e:
        return f"unknown ({e})"


def get_recent_actions():
    """Get last few auto_act results."""
    if not AUTO_ACT_LOG.exists():
        return "no actions logged"
    lines = AUTO_ACT_LOG.read_text().splitlines()
    cycles = [l for l in lines if "cycle complete" in l]
    if cycles:
        return cycles[-1].split("—")[-1].strip()
    return "no recent cycles"


def get_cascade_summary():
    """Get cascade sleeve P/L for session notes."""
    try:
        cascade_path = BASE / "core/cascade_ledger.py"
        if not cascade_path.exists():
            return None
        import sys
        if str(BASE) not in sys.path:
            sys.path.insert(0, str(BASE))
        from core.cascade_ledger import get_summary
        summary = get_summary()
        total = sum(s.get("realized_pl", 0) for s in summary.values())
        return f"Cascade: ${total:+.2f} realized"
    except Exception as e:
        return f"Cascade: unavailable ({e})"


def run():
    now = datetime.now()
    log(f"Writing session summary at {now.strftime('%Y-%m-%d %H:%M')}")

    focus = get_focus_from_changelog()
    trading = get_trade_summary()
    regret = get_regret_health()
    actions = get_recent_actions()
    cascade = get_cascade_summary()

    notes = f"Trading: {trading}. Regret index: {regret}. Recent actions: {actions}."
    if cascade:
        notes += f" {cascade}."

    summary = {
        "generated_at": now.isoformat(),
        "focus": focus,
        "notes": notes,
        "trading_status": trading,
        "regret_health": regret,
        "source": "auto_checkpoint",
        "generator": "session_checkpoint.py",
    }

    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(summary, indent=2))
    log(f"Written: {SESSION_FILE}")
    log(f"Next priority: {focus}")

    # Log to event ledger
    try:
        import sys
        if str(BASE) not in sys.path:
            sys.path.insert(0, str(BASE))
        from core.event_ledger import log_event
        log_event("system", "session_checkpoint", f"checkpoint written: {focus[:80]}", score=1.0)
    except Exception:
        pass


if __name__ == "__main__":
    run()
