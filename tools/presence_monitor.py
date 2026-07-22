#!/usr/bin/env python3
"""
tools/presence_monitor.py — Track whether Andrew is at the PC.
Writes memory/user_presence.json every 2 minutes.
Used by dispatcher to enable soldier mode when idle.
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
PRESENCE_FILE = BASE / "memory/user_presence.json"
SHIFT_LOG = BASE / "memory/shift_log.json"

IDLE_THRESHOLD_MS = 600_000  # 10 minutes


def get_idle_ms() -> int:
    try:
        result = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.gnome.Mutter.IdleMonitor",
             "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
             "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"],
            capture_output=True, text=True, timeout=5
        )
        raw = result.stdout.strip()
        # Output format: (uint64 60000,)
        ms = int(raw.replace("(uint64", "").replace(",)", "").strip())
        return ms
    except Exception:
        return 0


def load_presence() -> dict:
    if PRESENCE_FILE.exists():
        try:
            return json.loads(PRESENCE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_presence(data: dict):
    tmp = PRESENCE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(PRESENCE_FILE)


def load_shift_log() -> dict:
    if SHIFT_LOG.exists():
        try:
            return json.loads(SHIFT_LOG.read_text())
        except Exception:
            pass
    return {"shifts": [], "current_shift_start": None}


def save_shift_log(data: dict):
    tmp = SHIFT_LOG.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(SHIFT_LOG)


def run():
    idle_ms = get_idle_ms()
    is_idle = idle_ms >= IDLE_THRESHOLD_MS
    now = datetime.now().isoformat()

    prev = load_presence()
    was_idle = prev.get("is_idle", False)
    shift_log = load_shift_log()

    # Detect transition: active → idle (shift starts)
    if is_idle and not was_idle:
        shift_log["current_shift_start"] = now
        save_shift_log(shift_log)

    # Detect transition: idle → active (shift ends — trigger report)
    if not is_idle and was_idle and shift_log.get("current_shift_start"):
        shift_start = shift_log["current_shift_start"]
        try:
            start_dt = datetime.fromisoformat(shift_start)
            duration_min = int((datetime.now() - start_dt).total_seconds() / 60)
        except Exception:
            duration_min = 0

        # Record completed shift
        shift_log.setdefault("shifts", []).append({
            "start": shift_start,
            "end": now,
            "duration_min": duration_min,
        })
        shift_log["current_shift_start"] = None

        # Keep last 30 shifts
        shift_log["shifts"] = shift_log["shifts"][-30:]
        save_shift_log(shift_log)

        # Write return flag so telegram_intake can send the report
        return_flag = BASE / "memory/soldier_return_flag.json"
        return_flag.write_text(json.dumps({
            "shift_start": shift_start,
            "shift_end": now,
            "duration_min": duration_min,
            "ts": now,
        }))

    presence = {
        "idle_ms": idle_ms,
        "idle_minutes": idle_ms / 60000,
        "is_idle": is_idle,
        "updated_at": now,
        "shift_active": shift_log.get("current_shift_start") is not None,
        "shift_start": shift_log.get("current_shift_start"),
    }
    save_presence(presence)


if __name__ == "__main__":
    run()
