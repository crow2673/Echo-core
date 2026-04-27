#!/usr/bin/env python3
"""tools/core_state_writer.py — writes core_state_system.json every 30s."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "memory/core_state_system.json"

WORKERS = {
    "pulse":          {"service": "echo-pulse.service",          "interval": 86400},
    "heartbeat":      {"service": "echo-heartbeat.service",      "interval": 60},
    "self_act_worker":{"service": "echo-self-act-worker.service","interval": 300},
    "auto_act":       {"service": "echo-auto-act.service",       "interval": 1800},
    "ntfy_bridge":    {"service": "echo-ntfy-bridge.service",    "interval": None},
    "git_backup":     {"service": "echo-git-backup.service",     "interval": 86400},
    "disk_monitor":   {"service": "echo-disk-monitor.service",   "interval": 21600},
    "demand_scanner": {"service": "echo-demand-scanner.service", "interval": 3600},
    "crypto_trader":  {"service": "echo-crypto-trader.service",  "interval": 7200},
    "trader":         {"service": "echo-trader.service",         "interval": 14400},
    "session_checkpoint": {"service": "echo-session-checkpoint.service", "interval": 86400},
}

TIMERS = {
    "self_act_worker": "echo-self-act-worker.timer",
    "auto_act":        "echo-auto-act.timer",
    "pulse":           "echo-pulse.timer",
    "heartbeat":       "echo-heartbeat.timer",
    "git_backup":      "echo-git-backup.timer",
    "disk_monitor":    "echo-disk-monitor.timer",
    "demand_scanner":  "echo-demand-scanner.timer",
    "crypto_trader":   "echo-crypto-trader.timer",
    "ntfy_bridge":     "echo-ntfy-bridge.service",
}


def systemd_show(unit, props):
    try:
        r = subprocess.run(
            ["systemctl", "--user", "show", unit, "--property=" + ",".join(props)],
            capture_output=True, text=True, timeout=5
        )
        meta = {}
        for line in r.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                if k in props:
                    meta[k] = v
        return meta
    except Exception:
        return {}


def is_active(unit):
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


def get_core_procs():
    try:
        r = subprocess.run(
            ["pgrep", "-a", "-f", "echo_core_daemon"],
            capture_output=True, text=True, timeout=5
        )
        return [l.strip() for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        return []


def parse_timestamp(ts_str):
    if not ts_str or ts_str in ("n/a", ""):
        return None
    try:
        r = subprocess.run(
            ["date", "-d", ts_str, "--iso-8601=seconds"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() or None
    except Exception:
        return None


def build_worker(name, cfg):
    svc = cfg["service"]
    interval = cfg["interval"]
    props = ["Result", "ExecMainStartTimestamp", "ExecMainExitTimestamp",
             "ExecMainCode", "ExecMainStatus", "InactiveExitTimestamp"]
    meta = systemd_show(svc, props)

    last_exit = parse_timestamp(meta.get("ExecMainExitTimestamp", ""))
    now = datetime.now(timezone.utc)
    age_seconds = None
    stale = False

    if last_exit:
        try:
            from datetime import datetime as dt
            import re
            # parse ISO 8601 with timezone offset
            le = dt.fromisoformat(last_exit)
            age_seconds = int((now - le.astimezone(timezone.utc)).total_seconds())
            if interval and age_seconds > interval * 2.5:
                stale = True
        except Exception:
            pass

    result = meta.get("Result", "unknown")
    health = "ok" if result in ("success", "") else "degraded"
    if result == "failed":
        health = "failed"

    next_run = None
    if last_exit and interval:
        try:
            from datetime import timedelta
            le_dt = datetime.fromisoformat(last_exit)
            next_run = (le_dt + timedelta(seconds=interval)).isoformat()
        except Exception:
            pass

    return {
        "service": svc,
        "meta": {k: meta[k] for k in props if k in meta},
        "health": health,
        "expected_interval_seconds": interval,
        "last_exit_local": last_exit,
        "next_expected_run_local": next_run,
        "age_seconds": age_seconds,
        "stale": stale,
    }


def run():
    now = datetime.now(timezone.utc)
    state = {
        "updated_at": now.isoformat(),
        "updated_at_local": datetime.now().astimezone().isoformat(),
        "core": {
            "service": "echo-core.service",
            "status": is_active("echo-core.service"),
            "procs": get_core_procs(),
        },
        "timers": {name: is_active(svc) for name, svc in TIMERS.items()},
        "workers": {name: build_worker(name, cfg) for name, cfg in WORKERS.items()},
    }

    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(OUT)
    print(f"[core_state_writer] updated {OUT.name}", flush=True)


if __name__ == "__main__":
    run()
