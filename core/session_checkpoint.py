#!/usr/bin/env python3
"""
session_checkpoint.py — Phase 3B
Automatically writes session_summary.json at the end of each session.
Reads: CHANGELOG.md tail, auto_act.log, trade_log.json, regret_patterns.json
Writes: memory/session_summary.json
Governor reads this and embeds it into echo_state.json
Briefing reads it and speaks real context.
"""
import json
import subprocess
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "Echo"
SUMMARY_FILE = BASE / "memory/session_summary.json"
CHANGELOG = BASE / "CHANGELOG.md"
AUTO_ACT_LOG = BASE / "logs/auto_act.log"
TRADE_LOG = BASE / "memory/trade_log.json"
REGRET = BASE / "memory/regret_patterns.json"

def get_recent_changelog(lines=80):
    """Pull today's ## headers from CHANGELOG and join them into a focus statement.
    Filters noise, deduplicates, caps at 4 items.
    Respects override_focus field in existing session_summary.json.
    """
    # Check for human override first
    try:
        if SUMMARY_FILE.exists():
            existing = json.loads(SUMMARY_FILE.read_text())
            if existing.get("override_focus"):
                focus = existing["override_focus"]
                print(f"[checkpoint] Using override_focus: {focus[:60]}")
                decisions = existing.get("key_decisions", [])
                return focus, decisions
    except Exception:
        pass

    try:
        text = CHANGELOG.read_text().splitlines()
        recent = text[-lines:]

        # Collect all meaningful ## headers from recent lines
        noise = {"auto-act", "auto act", "auto backup", "session summary"}
        headers = []
        decisions = []
        for line in recent:
            if line.startswith("## "):
                header = line.replace("## ", "").strip()
                # Filter noise and duplicates
                if not any(n in header.lower() for n in noise):
                    # Shorten date prefix if present
                    if " — " in header:
                        header = header.split(" — ", 1)[1].strip()
                    if header not in headers:
                        headers.append(header)
            elif line.startswith("- ") and len(line) > 5:
                decisions.append(line[2:].strip())

        # Cap at 4 most recent unique headers
        headers = headers[-4:] if headers else ["Recent build work"]
        focus = " + ".join(headers)
        return focus, decisions[-6:] if decisions else []
    except Exception as e:
        return "Build session", [str(e)]

def get_next_priority():
    """Read TODO.md and find first unchecked high priority item."""
    try:
        todo = (BASE / "TODO.md").read_text().splitlines()
        in_high = False
        for line in todo:
            if "HIGH PRIORITY" in line.upper():
                in_high = True
            elif line.startswith("## ") and in_high:
                break
            elif in_high and line.startswith("- [ ]"):
                return line[5:].strip()
    except Exception:
        pass
    return "Continue Crown the King Phase 3B"

def get_trade_status():
    """Quick trade summary."""
    try:
        trades = json.loads(TRADE_LOG.read_text())
        open_trades = [t for t in trades if t.get("status") == "submitted"]
        if open_trades:
            symbols = [t.get("symbol") for t in open_trades]
            return f"{len(open_trades)} positions open: {', '.join(symbols)}"
        return "No open positions"
    except Exception:
        return "Trade status unknown"

def get_regret_status():
    """Check regret index health."""
    try:
        data = json.loads(REGRET.read_text())
        return "healthy" if data.get("healthy") else f"flagged: {data.get('flagged_categories', [])}"
    except Exception:
        return "unknown"

def get_auto_act_summary():
    """Get last few auto_act results."""
    try:
        lines = AUTO_ACT_LOG.read_text().splitlines()
        recent = [l for l in lines[-20:] if "EXECUTED" in l or "cycle complete" in l]
        return recent[-3:] if recent else []
    except Exception:
        return []

def write_checkpoint():
    print(f"[checkpoint] Writing session summary at {datetime.now().strftime('%H:%M:%S')}")
    
    focus, decisions = get_recent_changelog()
    next_priority = get_next_priority()
    trade_status = get_trade_status()
    regret_status = get_regret_status()
    auto_act = get_auto_act_summary()

    # Build notes from auto_act activity
    notes = f"Trading: {trade_status}. Regret index: {regret_status}."
    if auto_act:
        notes += f" Recent actions: {'; '.join(auto_act[-2:])}"

    summary = {
        "timestamp": datetime.now().isoformat(),
        "session_focus": focus,
        "key_decisions": decisions,
        "next_priority": next_priority,
        "status": "auto_checkpoint",
        "notes": notes,
        "generated_by": "session_checkpoint.py"
    }

    SUMMARY_FILE.write_text(json.dumps(summary, indent=2))
    print(f"[checkpoint] Written: {focus[:60]}")
    print(f"[checkpoint] Next priority: {next_priority[:60]}")

if __name__ == "__main__":
    write_checkpoint()
