#!/usr/bin/env python3
import json, subprocess, datetime
from pathlib import Path

STATE = Path.home()/"Echo/memory/core_state_system.json"
LOG   = Path.home()/"Echo/logs/core_state_autofix.log"

ALLOW = {
    "pulse":         {"timer": "echo-pulse.timer",              "service": "echo-pulse.service"},
    "reachability":  {"timer": "echo-reachability-watch.timer", "service": "echo-reachability-watch.service"},
    "golem_monitor": {"timer": "echo-golem-monitor.timer",      "service": "echo-golem-monitor.service"},
    "self_act_worker":{"timer":"echo-self-act-worker.timer",    "service": "echo-self-act-worker.service"},
    "heartbeat":     {"timer": "echo-heartbeat.timer",          "service": "echo-heartbeat.service"},
}

COOLDOWN_S = 120
STAMP = Path.home()/"Echo/memory/core_state_autofix_stamps.json"

def is_active(unit):
    out = sh(["systemctl","--user","is-active",unit])
    return out if out else "unknown"

def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()

def log(line):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().astimezone().isoformat()
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{ts} {line}\n")

def load_stamps():
    try:
        return json.loads(STAMP.read_text())
    except Exception:
        return {}

def save_stamps(stamps):
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(json.dumps(stamps, indent=2) + "\n")

def state_is_fresh(state, max_age_s=90):
    try:
        ts = state.get("updated_at") or state.get("updated_at_local")
        if not ts:
            return False
        ts = ts.replace("Z","+00:00")
        dt = datetime.datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - dt.astimezone(datetime.timezone.utc)).total_seconds()
        return age <= max_age_s
    except Exception:
        return False

def now_epoch():
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())

def main():
    if not STATE.exists():
        log("no-state-file: skip")
        return

    s = json.loads(STATE.read_text())
    workers = s.get("workers", {})
    if not state_is_fresh(s, max_age_s=90):
        log("state-too-old: skip (writer may be down)")
        return
    stamps = load_stamps()

    acted = []
    for name, w in workers.items():
        if name not in ALLOW:
            continue
        if not isinstance(w, dict):
            continue
        if w.get("stale") is not True:
            continue

        last = int(stamps.get(name, 0))
        if now_epoch() - last < COOLDOWN_S:
            log(f"cooldown: {name} stale=true (last={last})")
            continue

        timer = ALLOW[name]["timer"]
        service = ALLOW[name]["service"]

        # Tier-0: if timer is down, bring it back immediately (subject to cooldown)
        tstat = is_active(timer)
        if tstat != "active":
            log(f"timer-not-active-fast: {name} {timer}={tstat} -> restart; start {service}")
            sh(["systemctl","--user","restart",timer])
            t2 = is_active(timer)
            log(f"timer-post-restart: {name} {timer}={t2}")
            sh(["systemctl","--user","start",service])
            stamps[name] = now_epoch()
            acted.append(name)
            continue

        tstat = is_active(timer)
        if tstat != "active":
            log(f"stale-detected: {name} timer={timer} status={tstat} -> restart; start {service}")
            sh(["systemctl","--user","restart",timer])
        else:
            log(f"stale-detected: {name} timer={timer} status=active -> no-restart; start {service}")
        sh(["systemctl","--user","start",service])

        stamps[name] = now_epoch()
        acted.append(name)

    save_stamps(stamps)
    if not acted:
        log("no-action: all ok or cooldown")

if __name__ == "__main__":
    main()
