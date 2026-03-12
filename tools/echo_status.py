#!/usr/bin/env python3
from __future__ import annotations

import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path.home() / "Echo"
STATE = ROOT / "memory" / "core_state_system.json"

# Map your state keys -> actual systemd unit names
UNIT_MAP = {
    "pulse":         {"timer": "echo-pulse.timer",              "service": "echo-pulse.service"},
    "golem_monitor": {"timer": "echo-golem-monitor.timer",      "service": "echo-golem-monitor.service"},
    "reachability":  {"timer": "echo-reachability-watch.timer", "service": "echo-reachability-watch.service"},
    "heartbeat":     {"timer": "echo-heartbeat.timer",          "service": "echo-heartbeat.service"},
    "self_act_worker":{"timer":"echo-self-act-worker.timer",    "service": "echo-self-act-worker.service"},
    "auto_act":       {"timer":"echo-auto-act.timer",            "service": "echo-auto-act.service"},
    "ntfy_bridge":    {"timer":None,                              "service": "echo-ntfy-bridge.service"},
}

def sh(args: list[str]) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()

def fmt_age(seconds: int | float | None) -> str:
    if seconds is None:
        return "?"
    s = int(seconds)
    if s < 60: return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60: return f"{m}m {s}s"
    h, m = divmod(m, 60)
    if h < 48: return f"{h}h {m}m"
    d, h = divmod(h, 24)
    return f"{d}d {h}h"

def load_state() -> dict:
    if not STATE.exists():
        raise SystemExit(f"missing: {STATE}")
    return json.loads(STATE.read_text())

def unit_health(unit: str) -> dict:
    # Returns: active, sub, result, last_exit
    try:
        out = sh(["systemctl","--user","show",unit,
                  "-p","ActiveState","-p","SubState","-p","Result","-p","ExecMainExitTimestamp"])
    except Exception:
        return {"active":"unknown","sub":"unknown","result":"unknown","last_exit":None}

    kv = {}
    for line in out.splitlines():
        if "=" in line:
            k,v = line.split("=",1)
            kv[k]=v

    last_exit = kv.get("ExecMainExitTimestamp") or None
    # systemd uses "n/a" often
    if last_exit and last_exit.lower() == "n/a":
        last_exit = None

    return {
        "active": kv.get("ActiveState","unknown"),
        "sub": kv.get("SubState","unknown"),
        "result": kv.get("Result","unknown"),
        "last_exit": last_exit,
    }

def main():
    ap = argparse.ArgumentParser(description='Echo status')
    ap.add_argument('--json', action='store_true', help='Emit JSON only')
    ap.add_argument('--quiet', action='store_true', help='No human output; exit code only')
    args = ap.parse_args()

    s = load_state()

    core = (s.get('core') or {}).get('status', 'unknown')
    timers = s.get('timers', {}) or {}
    workers = s.get('workers', {}) or {}
    errors = s.get('errors', []) or []

    stale = 0
    for w in workers.values():
        if (w or {}).get('stale'):
            stale += 1
    inactive_timers = sum(1 for v in timers.values() if v != 'active')

    summary = {
        'updated_at_local': s.get('updated_at_local') or s.get('updated_at'),
        'core': core,
        'stale': stale,
        'inactive_timers': inactive_timers,
        'errors': len(errors),
        'timers': timers,
        'workers': workers,
    }

    ok = (core == 'active' and stale == 0 and inactive_timers == 0 and len(errors) == 0)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        raise SystemExit(0 if ok else 2)
    if args.quiet:
        raise SystemExit(0 if ok else 2)


    updated = s.get("updated_at_local") or s.get("updated_at")
    core = s.get("core", {}).get("status", "unknown")
    timers = s.get("timers", {}) or {}
    workers = s.get("workers", {}) or {}
    errors = s.get("errors", []) or []

    bad = 0

    # Header
    print("=== ECHO STATUS ===")
    print(f"updated_at_local: {updated}")
    print(f"core: {core}")
    print("")

    # One-line summary (OK / NOT OK)
    stale_workers = [k for k,v in workers.items() if (v or {}).get("stale") is True]
    inactive_timers = [k for k,v in timers.items() if v != "active"]
    if core != "active" or errors or stale_workers or inactive_timers:
        print(f"SUMMARY: NOT OK ❌  core={core}  stale={len(stale_workers)}  inactive_timers={len(inactive_timers)}  errors={len(errors)}")
        bad = 1
    else:
        print("SUMMARY: OK ✅  core=active  stale=0  inactive_timers=0  errors=0")
    print("")

    # Timers
    print("Timers:")
    for k in sorted(timers.keys()):
        v = timers[k]
        mark = "✅" if v == "active" else "⚠️"
        print(f"  {mark} {k:14s} {v}")
    print("")

    # Workers
    print("Workers:")
    for name in sorted(workers.keys()):
        w = workers[name] or {}
        stale = bool(w.get("stale", False))
        age = w.get("age_seconds", None)
        nxt = w.get("next_expected_run_local", None)
        mark = "✅" if not stale else "❌"
        print(f"  {mark} {name:14s} age={fmt_age(age):>8s}  next={nxt}")
    print("")

    # systemd health (timer + service per worker)
    print("systemd health:")
    for key in sorted(UNIT_MAP.keys()):
        t = UNIT_MAP[key]["timer"]
        sv = UNIT_MAP[key]["service"]

        shh = unit_health(sv)
        smark = "✅" if shh["result"] in ("success","") or shh["active"] in ("active","inactive") else "⚠️"
        print(f"  {key}:")
        if t:
            th = unit_health(t)
            tmark = "✅" if th["active"] == "active" else "⚠️"
            print(f"    {tmark} timer   {t:28s}  {th['active']}/{th['sub']}")
        else:
            print(f"    — timer   (none — persistent service)")
        print(f"    {smark} service {sv:28s}  {shh['active']}/{shh['sub']}  result={shh['result']}  last_exit={shh['last_exit']}")
    print("")

    if errors:
        print("Errors:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("Errors: none ✅")

    raise SystemExit(2 if bad else 0)

if __name__ == "__main__":
    main()
