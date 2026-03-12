#!/usr/bin/env python3
import json, subprocess, datetime, re
import re
from pathlib import Path

ECHO = Path.home() / "Echo"
STATE = ECHO / "memory" / "core_state_system.json"
PULSE = ECHO / "memory" / "experience_log.jsonl"
MEM = ECHO / "echo_memory.json"

def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()

def is_active(unit):
    out = sh(["systemctl","--user","is-active",unit])
    return out if out else "unknown"


def timer_next_elapse(timer_unit: str):
    """
    Returns ISO local datetime string for next timer elapse if available, else None.

    Prefer:
      systemctl show <timer> -p NextElapseUSecRealtime
    Fallback:
      systemctl list-timers --all --no-legend --no-pager <timer>

    NOTE: We ignore timezone abbreviations (e.g. CST) and interpret as local time,
    because %Z parsing is inconsistent across systems.
    """
    def parse_ts_tokens(parts):
        # With weekday: Sun 2026-02-22 00:05:00 CST ...
        # Without weekday: 2026-02-22 00:05:00 CST ...
        if len(parts) < 3:
            return None
        if re.match(r"^[A-Za-z]{3}$", parts[0]):
            # take: Day YYYY-MM-DD HH:MM:SS (ignore TZ token)
            core = " ".join(parts[0:3])  # Day + date + time
            fmt = "%a %Y-%m-%d %H:%M:%S"
        else:
            # take: YYYY-MM-DD HH:MM:SS (ignore TZ token)
            core = " ".join(parts[0:2])  # date + time
            fmt = "%Y-%m-%d %H:%M:%S"
        try:
            dt = datetime.datetime.strptime(core, fmt)
            # interpret as local time
            return dt.astimezone()
        except Exception:
            return None

    # 1) show property
    try:
        raw = sh(["systemctl","--user","show",timer_unit,"-p","NextElapseUSecRealtime"])
        if raw and "=" in raw:
            _, ts = raw.split("=", 1)
            ts = ts.strip()
            if ts:
                parts = ts.split()
                dt = parse_ts_tokens(parts)
                return dt.isoformat() if dt else None
    except Exception:
        pass

    # 2) list-timers fallback
    try:
        line = sh(["systemctl","--user","list-timers","--all","--no-legend","--no-pager", timer_unit])
        if not line:
            return None
        parts = line.split()
        dt = parse_ts_tokens(parts)
        return dt.isoformat() if dt else None
    except Exception:
        return None

def meta_health(meta):
    # meta dict from unit_props()
    if not isinstance(meta, dict) or not meta:
        return "unknown"
    if meta.get("Result") == "success" and meta.get("ExecMainStatus") == "0":
        return "ok"
    return "fail"

def unit_props(unit, props):
    # props: list like ["Result","ExecMainStatus",...]
    out = {}
    try:
        q = ["systemctl","--user","show",unit] + sum([["-p",x] for x in props], [])
        raw = sh(q)
        for line in raw.splitlines():
            if "=" in line:
                k,v = line.split("=",1)
                out[k] = v
    except Exception:
        pass
    return out


def parse_systemd_ts(ts: str):
    """
    Parse systemd timestamps like:
      'Sat 2026-02-21 16:13:50 CST'
      '2026-02-21 16:13:50 CST'
    Returns aware datetime, best-effort.
    """
    if not ts or not isinstance(ts, str):
        return None
    ts = ts.strip()
    if not ts or ts == "n/a":
        return None

    parts = ts.split()
    # need at least: [Day] YYYY-MM-DD HH:MM:SS TZ  OR  YYYY-MM-DD HH:MM:SS TZ
    if len(parts) < 3:
        return None

    # If there is no timezone token, assume local
    tz = None
    if len(parts) >= 4:
        tz = parts[-1]
        core_parts = parts[:-1]
    else:
        core_parts = parts

    # core could be: ['Sat','2026-02-21','16:13:50'] or ['2026-02-21','16:13:50']
    if len(core_parts) == 3 and re.match(r"^[A-Za-z]{3}$", core_parts[0]):
        core = " ".join(core_parts)
        fmts = ["%a %Y-%m-%d %H:%M:%S"]
    else:
        core = " ".join(core_parts)
        fmts = ["%Y-%m-%d %H:%M:%S"]

    dt = None
    for fmt in fmts:
        try:
            dt = datetime.datetime.strptime(core, fmt)
            break
        except Exception:
            continue
    if dt is None:
        return None

    if tz:
        tz_map = {"CST": -6, "CDT": -5, "UTC": 0, "GMT": 0}
        if tz in tz_map:
            off = datetime.timedelta(hours=tz_map[tz])
            return dt.replace(tzinfo=datetime.timezone(off))

    return dt.replace(tzinfo=datetime.datetime.now().astimezone().tzinfo)


def worker_snapshot(service_unit: str, expected_interval_s=None, timer_unit=None):
    """
    One-shot capture: meta once, health derived from same meta,
    plus staleness based on last exit timestamp (best-effort).
    """
    props = ["Result","ExecMainStatus","ExecMainCode",
             "ExecMainStartTimestamp","ExecMainExitTimestamp","InactiveExitTimestamp"]
    meta = unit_props(service_unit, props)

    health = meta_health({"Result": meta.get("Result"), "ExecMainStatus": meta.get("ExecMainStatus")})

    last_ts = meta.get("ExecMainExitTimestamp") or meta.get("InactiveExitTimestamp") or ""
    last_dt = parse_systemd_ts(last_ts)
    age_s = None
    stale = None
    last_exit_local = None

    if last_dt is not None:
        now_local = datetime.datetime.now().astimezone()
        # normalize last_dt into local tz for reporting
        last_local = last_dt.astimezone(now_local.tzinfo)
        last_exit_local = last_local.isoformat()
        age_s = int(max(0, (now_local - last_local).total_seconds()))
        if expected_interval_s is not None:
            # stale if > 2x expected interval (gives breathing room for jitter)
            stale = age_s > (expected_interval_s * 2)

    snap = {
        "service": service_unit,
        "meta": meta,
        "health": health,
    }
    if expected_interval_s is not None:
        snap["expected_interval_seconds"] = int(expected_interval_s)
    if last_exit_local is not None:
        snap["last_exit_local"] = last_exit_local
    # Prefer timer schedule for next run (more accurate than last_exit+interval)
    next_local = timer_next_elapse(timer_unit) if timer_unit else None
    next_dt = (last_dt + datetime.timedelta(seconds=expected_interval_s)) if (last_dt and expected_interval_s) else None
    snap["next_expected_run_local"] = next_local or (next_dt.isoformat() if next_dt else None)

    if age_s is not None:
        snap["age_seconds"] = age_s
    if stale is not None:
        snap["stale"] = stale
    return snap

def pgrep(pattern):
    out = sh(["pgrep","-af",pattern])
    return out.splitlines() if out else []

def tail1(path):
    try:
        lines = path.read_text().splitlines()
        return lines[-1] if lines else None
    except FileNotFoundError:
        return None

def read_last_command():
    try:
        data = json.loads(MEM.read_text())
        # last object in file is fine, but we'll scan backward for safety
        for x in reversed(data):
            if isinstance(x, dict) and x.get("type") == "command":
                return x
        return None
    except Exception:
        return None

now = datetime.datetime.now(datetime.timezone.utc).isoformat()

core_procs = pgrep("echo_core_daemon.py")
last_pulse = tail1(PULSE)
last_cmd = read_last_command()

state = {
    "updated_at": now,
    "updated_at_local": datetime.datetime.now().astimezone().isoformat(),
    "core": {
        "service": "echo-core.service",
        "status": is_active("echo-core.service"),
        "procs": core_procs[:3],
    },
    "services": {
        "golem_provider": is_active("golem-provider.service"),

    },
    "timers": {
        "self_act_worker": is_active("echo-self-act-worker.timer"),
        "pulse": is_active("echo-pulse.timer"),
        "reachability": is_active("echo-reachability-watch.timer"),
        "golem_monitor": is_active("echo-golem-monitor.timer"),
        "heartbeat": is_active("echo-heartbeat.timer"),
        "auto_act": is_active("echo-auto-act.timer"),
        "ntfy_bridge": is_active("echo-ntfy-bridge.service"),

    },

    "workers": {
      "pulse": worker_snapshot("echo-pulse.service", expected_interval_s=86400, timer_unit="echo-pulse.timer"),
      "reachability": worker_snapshot("echo-reachability-watch.service", expected_interval_s=300, timer_unit="echo-reachability-watch.timer"),
      "golem_monitor": worker_snapshot("echo-golem-monitor.service", expected_interval_s=86400, timer_unit="echo-golem-monitor.timer"),
      "heartbeat": worker_snapshot("echo-heartbeat.service", expected_interval_s=60, timer_unit="echo-heartbeat.timer"),
      "self_act_worker": worker_snapshot("echo-self-act-worker.service", expected_interval_s=300, timer_unit="echo-self-act-worker.timer"),
      "auto_act": worker_snapshot("echo-auto-act.service", expected_interval_s=1800, timer_unit="echo-auto-act.timer"),
      "ntfy_bridge": worker_snapshot("echo-ntfy-bridge.service", expected_interval_s=None)

    },
    "last": {
        "pulse_line": last_pulse,
        "command": last_cmd,
    },
    "errors": []
}

def main():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    print("[ok] wrote", STATE)

if __name__ == "__main__":
    main()
