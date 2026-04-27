#!/usr/bin/env python3
"""
tools/ollama_watchdog.py — Restart Ollama if it stops responding.
Runs every 10 minutes via echo-ollama-watchdog.timer.
"""
import json
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LOG = BASE / "logs/ollama_watchdog.log"
OLLAMA_URL = "http://localhost:11434/api/tags"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def ollama_alive():
    try:
        req = urllib.request.Request(OLLAMA_URL)
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            models = data.get("models", [])
            return True, len(models)
    except Exception as e:
        return False, str(e)


def restart_ollama():
    log("Attempting to restart Ollama...")
    result = subprocess.run(
        ["systemctl", "restart", "ollama"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        log("Ollama restarted via systemctl")
        return True
    # Try user service
    result = subprocess.run(
        ["systemctl", "--user", "restart", "ollama"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        log("Ollama restarted via systemctl --user")
        return True
    log(f"Restart failed: {result.stderr}")
    return False


def run():
    alive, info = ollama_alive()
    if alive:
        log(f"Ollama OK — {info} models loaded")
        return

    log(f"Ollama not responding: {info}")

    restarted = restart_ollama()
    if restarted:
        import time
        time.sleep(10)
        alive2, info2 = ollama_alive()
        if alive2:
            log(f"Ollama recovered — {info2} models available")
            try:
                from core.notifier import notify
                notify("Ollama Recovered", f"Watchdog restarted Ollama — {info2} models", urgent=False)
            except Exception:
                pass
        else:
            log(f"Ollama still down after restart: {info2}")
            try:
                from core.notifier import notify
                notify("Ollama DOWN", f"Watchdog could not recover Ollama: {info2}", urgent=True)
            except Exception:
                pass
    else:
        try:
            from core.notifier import notify
            notify("Ollama DOWN", f"Ollama not responding and restart failed: {info}", urgent=True)
        except Exception:
            pass


if __name__ == "__main__":
    run()
