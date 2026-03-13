#!/usr/bin/env python3
"""
Golem pricing adjustment utility.
Echo can call this to adjust pricing on all presets.

Usage:
    python3 -m core.golem_pricing --cpu 0.00010 --duration 0.00003
    python3 -m core.golem_pricing --preset vm --cpu 0.00010 --duration 0.00003
    python3 -m core.golem_pricing --status
"""
import subprocess, json, sys, argparse
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/golem_pricing.log"

PRESETS = ["default", "vm", "wasmtime"]

# Safe bounds — Echo can't set insane values
CPU_MIN, CPU_MAX = 0.00001, 0.001
DUR_MIN, DUR_MAX = 0.00001, 0.001

def log(msg):
    LOG.parent.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def get_current():
    result = subprocess.run(
        ["ya-provider", "preset", "list", "--json"],
        capture_output=True, text=True
    )
    lines = [l for l in result.stdout.splitlines() if l.startswith("[") or l.startswith("{") or l.startswith("]") or l.strip().startswith("{") or l.strip().startswith("}") or l.strip().startswith('"')]
    # Filter out log lines, find JSON
    json_start = result.stdout.find("[")
    if json_start == -1:
        return []
    try:
        return json.loads(result.stdout[json_start:])
    except Exception:
        return []

def set_pricing(cpu, duration, preset=None):
    targets = [preset] if preset else PRESETS
    if not (CPU_MIN <= cpu <= CPU_MAX):
        log(f"REFUSED: cpu {cpu} out of safe range [{CPU_MIN}, {CPU_MAX}]")
        return False
    if not (DUR_MIN <= duration <= DUR_MAX):
        log(f"REFUSED: duration {duration} out of safe range [{DUR_MIN}, {DUR_MAX}]")
        return False

    for p in targets:
        cmd = [
            "ya-provider", "preset", "update",
            "--no-interactive",
            "--name", p,
            "--price", f"cpu={cpu}",
            "--price", f"duration={duration}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            log(f"preset '{p}' updated: cpu={cpu} duration={duration}")
        else:
            log(f"preset '{p}' FAILED: {result.stderr.strip()[:200]}")
            return False

    # Log to event ledger
    try:
        sys.path.insert(0, str(BASE))
        from core.event_ledger import log_event
        log_event("income", "golem_pricing",
            f"pricing updated: cpu={cpu} duration={duration} presets={targets}",
            score=1.0)
    except Exception:
        pass

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu", type=float, help="CPU price per second in GLM")
    parser.add_argument("--duration", type=float, help="Duration price per second in GLM")
    parser.add_argument("--preset", type=str, help="Specific preset (default: all)")
    parser.add_argument("--status", action="store_true", help="Show current pricing")
    args = parser.parse_args()

    if args.status:
        presets = get_current()
        for p in presets:
            cpu = p["usage-coeffs"].get("golem.usage.cpu_sec", "?")
            dur = p["usage-coeffs"].get("golem.usage.duration_sec", "?")
            print(f"{p['name']}: cpu={cpu} duration={dur}")
    elif args.cpu and args.duration:
        ok = set_pricing(args.cpu, args.duration, args.preset)
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()
