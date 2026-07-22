#!/usr/bin/env python3
"""
governor_v2.py — Echo's System Truth Engine
Chain of command:
  echo_core_daemon.py  ← KING
  governor_v2.py       ← EYES (this file)
  workers/timers       ← HANDS

Writes ~/Echo/memory/echo_state.json every 5 minutes.
Everything else reads from this one file.
Observation only — no decisions, no restarts.
"""
import json
import subprocess
import os
import tempfile
import re
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "Echo"
STATE_FILE = BASE / "memory/echo_state.json"

def get_failed_units():
    """Return failed Echo user services instead of treating active timers as health."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "--failed", "--no-legend", "--plain"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip() or "systemctl failed", "units": []}
        units = []
        for line in result.stdout.splitlines():
            unit = line.split(maxsplit=1)[0] if line.strip() else ""
            if unit.startswith("echo-"):
                units.append(unit)
        return {"units": sorted(units), "count": len(units)}
    except Exception as e:
        return {"error": str(e), "units": []}


def get_timer_states():
    """Read all echo timer last-run times from systemd."""
    timers = {}
    def parse_passed_seconds(line: str):
        """Parse systemd's PASSED phrases: '13s ago', '1min 57s ago', '2h 44min ago'."""
        if "ago" not in line:
            return None
        before = line.rsplit(" ago", 1)[0]
        # Keep the final duration tokens before "ago"; ignore date/time columns.
        total = 0.0
        found = False
        for amount, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(ms|us|s|min|h|day|days|week|weeks)", before):
            found = True
            value = float(amount)
            if unit == "us":
                total += value / 1_000_000
            elif unit == "ms":
                total += value / 1000
            elif unit == "s":
                total += value
            elif unit == "min":
                total += value * 60
            elif unit == "h":
                total += value * 3600
            elif unit in ("day", "days"):
                total += value * 86400
            elif unit in ("week", "weeks"):
                total += value * 604800
        return int(total) if found else None

    try:
        result = subprocess.run(
            ["systemctl", "--user", "list-timers", "--all", "--no-pager"],
            capture_output=True, text=True, timeout=10
        )
        now = datetime.now()
        for line in result.stdout.splitlines():
            if "echo-" not in line:
                continue
            parts = line.split()
            # Find the service name
            svc = next((p for p in parts if p.startswith("echo-") and p.endswith(".service")), None)
            if not svc:
                continue
            name = svc.replace(".service", "")
            # Find PASSED column — look for "ago" in line
            last_run = None
            age_seconds = parse_passed_seconds(line)
            # Determine expected interval and health
            intervals = {
                "echo-heartbeat": 60,
                "echo-core-state": 60,
                "echo-core-state-writer": 30,
                "echo-core-state-autofix": 60,
                "echo-self-act-worker": 300,
                "echo-watchdog": 600,
                "echo-reachability-watch": 300,
                "echo-governor": 300,
                "echo-governor-v2": 3600,
                "echo-auto-act": 1800,
                "echo-trader": 345600,  # Mon-Fri 3x/day; up to 96h gap over weekend
                "echo-crypto-trader": 7200,
                "echo-analytics": 86400,
                "echo-daily-briefing": 86400,
                "echo-session-checkpoint": 86400,
                "echo-publish-weekly": 604800,
                "echo-vast-monitor": 86400,
                "echo-disk-monitor": 21600,
                "echo-git-backup": 86400,
                "echo-pulse": 86400,
                "echo-income-research": 604800,
                "echo-task-pruner": 604800,
                "echo-tech-scout": 604800,
                "echo-registry-update": 604800,
                "echo-weekly-report": 604800,
                "echo-initiative": 900,
                "echo-demand-scanner": 3600,
                "echo-gmail-scanner": 3600,
                "echo-outcome-reviewer": 1800,
                "echo-outlier-scanner": 14400,
                "echo-content-gen": 604800,
                "echo-telegram-intake": 30,
                "echo-devto-publish": 604800,
                "echo-ollama-watchdog": 600,
                "echo-daily-summary": 86400,
                "echo-offsite-backup": 86400,
                "echo-finetune": 2592000,
                "echo-temperature-monitor": 3600,
                "echo-cpu-monitor": 3600,
                "echo-system-health": 86400,
                "echo-inner-voice": 28800,
            }
            # Unknown/generated timers are commonly daily. Treating every unknown
            # timer as hourly creates false degradation for healthy daily jobs.
            expected = intervals.get(name, 86400)
            if age_seconds is not None:
                status = "healthy" if age_seconds < expected * 2 else "stale"
            else:
                status = "unknown"
            timers[name] = {
                "status": status,
                "age_seconds": age_seconds,
                "expected_interval": expected
            }
    except Exception as e:
        timers["_error"] = str(e)
    return timers

def get_system_stats():
    """Live CPU/RAM/swap/GPU via psutil and nvidia-smi."""
    stats = {}
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()
        stats["cpu_pct"] = cpu
        stats["ram_used_gb"] = round(ram.used / 1024**3, 1)
        stats["ram_total_gb"] = round(ram.total / 1024**3, 1)
        stats["ram_pct"] = ram.percent
        stats["swap_used_gb"] = round(swap.used / 1024**3, 1)
        stats["swap_total_gb"] = round(swap.total / 1024**3, 1)
    except Exception as e:
        stats["psutil_error"] = str(e)
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        parts = result.stdout.strip().split(",")
        if len(parts) == 3:
            stats["gpu_pct"] = int(parts[0].strip())
            stats["vram_used_mb"] = int(parts[1].strip())
            stats["vram_total_mb"] = int(parts[2].strip())
    except Exception as e:
        stats["gpu_error"] = str(e)
    return stats

def get_trade_snapshot():
    """Quick income snapshot from trade log."""
    snapshot = {
        "positions_open": 0,
        "last_trade_time": None,
        "portfolio_value": None,
        "profit_today": 0
    }
    try:
        trade_log = BASE / "memory/trade_log.json"
        if trade_log.exists():
            trades = json.loads(trade_log.read_text())
            open_trades = [t for t in trades if t.get("status") == "submitted"]
            snapshot["positions_open"] = len(open_trades)
            if trades:
                snapshot["last_trade_time"] = trades[-1].get("submitted_at")
    except Exception as e:
        snapshot["error"] = str(e)
    return snapshot

def get_trace_snapshot():
    """Get decision trace stats for echo_state."""
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("decision_trace", BASE / "core/decision_trace.py")
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        return _mod.get_summary_stats()
    except Exception as e:
        return {"error": str(e)}

def get_cascade_snapshot():
    """Get cascade sleeve summary for echo_state."""
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "cascade_ledger",
            BASE / "core/cascade_ledger.py"
        )
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        ledger = _mod.load_ledger()
        summary = {}
        for i in range(1, 5):
            key = str(i)
            s = ledger[key]
            closed = s["wins"] + s["losses"]
            hit = round(s["wins"] / closed * 100, 1) if closed else 0
            summary[f"layer_{i}"] = {
                "name": s["name"],
                "realized_pl": round(s["realized_pl"], 2),
                "total_trades": s["total_trades"],
                "hit_rate_pct": hit
            }
        return summary
    except Exception as e:
        return {"error": str(e)}

def get_regret_snapshot():
    """Regret index health summary."""
    try:
        import sqlite3
        db = sqlite3.connect(BASE / "memory/echo_events.db")
        total = db.execute("SELECT COUNT(*) FROM regret_index").fetchone()[0]
        unresolved = db.execute(
            "SELECT COUNT(*) FROM regret_index WHERE resolved_at IS NULL"
        ).fetchone()[0]
        db.close()
        p = BASE / "memory/regret_patterns.json"
        flags = []
        if p.exists():
            data = json.loads(p.read_text())
            flags = data.get("flags", [])
        status = "inactive" if total == 0 else ("flagged" if flags else "stable")
        return {
            "healthy": total > 0 and not flags,
            "entries": total,
            "unresolved": unresolved,
            "flagged_count": len(flags),
            "status": status,
        }
    except Exception as e:
        return {
            "healthy": False,
            "entries": 0,
            "unresolved": 0,
            "flagged_count": 0,
            "status": "error",
            "error": str(e),
        }

def get_golem_snapshot():
    """Check yagna wallet balance."""
    try:
        result = subprocess.run(
            ["yagna", "payment", "accounts"],
            capture_output=True, text=True, timeout=5
        )
        return {"status": "running", "raw": result.stdout[:100]}
    except Exception:
        return {"status": "unknown"}

def get_session_context():
    """Read session_summary.json and return as session_context dict."""
    try:
        p = Path.home() / "Echo/memory/session_summary.json"
        if not p.exists():
            return {"source": "missing", "session_focus": "No session summary found"}
        data = json.loads(p.read_text())
        return {
            "source": "session_summary.json",
            "session_focus": data.get("session_focus", "unknown"),
            "next_priority": data.get("next_priority", "unknown"),
            "key_decisions": data.get("key_decisions", []),
            "status": data.get("status", "unknown"),
            "notes": data.get("notes", ""),
            "timestamp": data.get("timestamp", "unknown")
        }
    except Exception as e:
        return {"source": "error", "error": str(e), "session_focus": "Session context unavailable"}

def write_state_atomic(state):
    """Write JSON atomically — prevents partial writes."""
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str))
    tmp.rename(STATE_FILE)

def run():
    print(f"[governor_v2] collecting state at {datetime.now().strftime('%H:%M:%S')}")

    state = {
        "timestamp": datetime.now().isoformat(),
        "session_context": get_session_context(),
        "generated_by": "governor_v2",
        "version": "v1",
        "valid": True,
        "system": get_system_stats(),
        "failed_units": get_failed_units(),
        "timers": get_timer_states(),
        "income": get_trade_snapshot(),
        "cascade": get_cascade_snapshot(),
        "decision_trace": get_trace_snapshot(),
        "regret_index": get_regret_snapshot(),
        "golem": get_golem_snapshot(),
    }

    # Overall health
    stale_timers = [
        k for k, v in state["timers"].items()
        if isinstance(v, dict) and v.get("status") == "stale"
    ]
    failed_units = state["failed_units"].get("units", [])
    errors = []
    if stale_timers:
        errors.append({"stale_timers": stale_timers})
    if failed_units:
        errors.append({"failed_units": failed_units})
    if state["failed_units"].get("error"):
        errors.append({"failed_unit_check": state["failed_units"]["error"]})
    if state["regret_index"].get("status") in ("inactive", "error"):
        errors.append({"regret_index": state["regret_index"]["status"]})

    state["system_health"] = "OK" if not errors else "DEGRADED"
    state["last_errors"] = errors

    write_state_atomic(state)
    print(f"[governor_v2] echo_state.json written — health={state['system_health']}")
    # Keep soul document current with live data
    try:
        import subprocess
        subprocess.Popen(
            ["python3", str(Path.home() / "Echo/core/update_contract.py")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

if __name__ == "__main__":
    run()
