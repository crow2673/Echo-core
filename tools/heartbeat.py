#!/usr/bin/env python3
import json, datetime, subprocess
from pathlib import Path

ECHO = Path.home()/"Echo"
LOG  = ECHO/"memory/experience_log.jsonl"

def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()

def is_active(unit):
    out = sh(["systemctl","--user","is-active",unit])
    return out if out else "unknown"

def main():
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    now_local = datetime.datetime.now().astimezone().isoformat()
    entry = {
        "ts": now_utc,
        "type": "heartbeat",
        "source": "echo-heartbeat.service",
        "ts_local": now_local,
        "ts_local": now_local,
        "core": is_active("echo-core.service"),
        "self_act_timer": is_active("echo-self-act-worker.timer"),
        "reachability_timer": is_active("echo-reachability-watch.timer"),
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

if __name__ == "__main__":
    main()
