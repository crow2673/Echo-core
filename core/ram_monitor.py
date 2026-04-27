#!/usr/bin/env python3
"""core/ram_monitor.py — monitors RAM and swap, alerts before OOM kills qwen2.5:32b."""
import json
import psutil
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/ram_monitor.log"
STATE_FILE = BASE / "memory/ram_monitor_state.json"

# qwen2.5:32b needs ~20GB; alert when available drops below threshold
WARN_AVAILABLE_GB = 4.0   # ntfy warning
CRIT_AVAILABLE_GB = 2.0   # ntfy urgent + log recommendation
SWAP_WARN_PCT = 70         # swap heavily used = pressure indicator

# Cooldown: don't spam alerts (seconds)
ALERT_COOLDOWN = 900  # 15 minutes


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_alert_ts": 0, "last_level": "ok"}


def save_state(state):
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(STATE_FILE)


def send_alert(title, msg, urgent=False):
    try:
        import sys
        if str(BASE) not in sys.path:
            sys.path.insert(0, str(BASE))
        from core.notifier import notify
        notify(title, msg, urgent=urgent)
    except Exception as e:
        log(f"notify failed: {e}")


def get_ollama_ram_mb():
    """Estimate RAM used by ollama/qwen processes."""
    total = 0
    try:
        for proc in psutil.process_iter(["name", "memory_info"]):
            if proc.info["name"] and "ollama" in proc.info["name"].lower():
                total += proc.info["memory_info"].rss
    except Exception:
        pass
    return total // 1024 // 1024


def run():
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()

    avail_gb = vm.available / 1024 / 1024 / 1024
    total_gb = vm.total / 1024 / 1024 / 1024
    used_pct = vm.percent
    swap_pct = swap.percent
    ollama_mb = get_ollama_ram_mb()

    log(
        f"RAM: {avail_gb:.1f}GB avail / {total_gb:.0f}GB total "
        f"({used_pct:.0f}% used) | swap: {swap_pct:.0f}% | ollama: {ollama_mb}MB"
    )

    state = load_state()
    now = datetime.now().timestamp()
    since_alert = now - state.get("last_alert_ts", 0)

    level = "ok"
    # Critical: low RAM + heavy swap (both required — swap alone is normal with lots of RAM free)
    if avail_gb < CRIT_AVAILABLE_GB and swap_pct >= SWAP_WARN_PCT:
        level = "critical"
    elif avail_gb < WARN_AVAILABLE_GB:
        level = "warn"
    elif avail_gb < WARN_AVAILABLE_GB * 1.5 and swap_pct >= SWAP_WARN_PCT:
        level = "warn"

    if level != "ok" and since_alert > ALERT_COOLDOWN:
        if level == "critical":
            msg = (
                f"RAM critical: {avail_gb:.1f}GB available, swap {swap_pct:.0f}% used. "
                f"Ollama using {ollama_mb}MB. qwen2.5:32b may OOM soon."
            )
            log(f"CRITICAL ALERT: {msg}")
            send_alert("Echo RAM Critical", msg, urgent=True)
        else:
            msg = (
                f"RAM low: {avail_gb:.1f}GB available ({used_pct:.0f}% used). "
                f"Ollama using {ollama_mb}MB."
            )
            log(f"WARN ALERT: {msg}")
            send_alert("Echo RAM Warning", msg, urgent=False)

        state["last_alert_ts"] = now
        state["last_level"] = level
        save_state(state)
    elif level == "ok" and state.get("last_level") != "ok":
        log("RAM back to normal")
        state["last_level"] = "ok"
        save_state(state)
    else:
        if level != "ok":
            log(f"RAM {level} suppressed (cooldown {int(since_alert)}s < {ALERT_COOLDOWN}s)")
        else:
            log(f"RAM OK")


if __name__ == "__main__":
    run()
