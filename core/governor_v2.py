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
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "Echo"
STATE_FILE = BASE / "memory/echo_state.json"

def get_timer_states():
    """Read all echo timer last-run times from systemd."""
    timers = {}
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
            age_seconds = None
            if "ago" in line:
                try:
                    # Extract the timestamp before "ago"
                    idx = parts.index("ago")
                    # Parse time like "5min", "1h", "30s"
                    passed_str = parts[idx-1]
                    if "min" in passed_str:
                        age_seconds = int(passed_str.replace("min", "")) * 60
                    elif "s" in passed_str and "h" not in passed_str:
                        age_seconds = int(passed_str.replace("s", ""))
                    elif "h" in passed_str:
                        age_seconds = int(passed_str.replace("h", "")) * 3600
                    elif "day" in passed_str:
                        age_seconds = int(parts[idx-2]) * 86400
                except Exception:
                    pass
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
                "echo-auto-act": 1800,
                "echo-trader": 14400,
                "echo-analytics": 86400,
                "echo-daily-briefing": 86400,
                "echo-publish-weekly": 604800,
                "echo-golem-monitor": 3600,
                "echo-vast-monitor": 3600,
                "echo-disk-monitor": 21600,
                "echo-git-backup": 86400,
                "echo-pulse": 86400,
                "echo-income-research": 604800,
                "echo-registry-update": 604800,
            }
            expected = intervals.get(name, 3600)
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
        p = BASE / "memory/regret_patterns.json"
        if p.exists():
            data = json.loads(p.read_text())
            return {
                "healthy": data.get("healthy", True),
                "flagged_count": len(data.get("flagged_categories", [])),
                "status": "stable" if data.get("healthy") else "flagged"
            }
    except Exception:
        pass
    return {"healthy": True, "flagged_count": 0, "status": "unknown"}

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
        "timers": get_timer_states(),
        "income": get_trade_snapshot(),
        "cascade": get_cascade_snapshot(),
        "regret_index": get_regret_snapshot(),
        "golem": get_golem_snapshot(),
    }

    # Overall health
    stale_timers = [k for k, v in state["timers"].items()
                    if v.get("status") == "stale"]
    state["system_health"] = "OK" if not stale_timers else f"STALE: {stale_timers}"
    state["last_errors"] = stale_timers

    write_state_atomic(state)
    print(f"[governor_v2] echo_state.json written — health={state['system_health']}")

if __name__ == "__main__":
    run()
