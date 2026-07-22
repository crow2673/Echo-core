#!/usr/bin/env python3
"""core/circuit_breaker.py — the hands the governor doesn't have.

governor_v2 is "observation only — no decisions, no restarts." It SAW the
runaway event/LLM loop that bloated echo_memory.json to 374MB and had to be
hand-fixed; it could not STOP it. This is the missing safety loop (Q6): a guard
with real authority to halt a runaway worker BEFORE damage.

Trips on:
  • EVENT STORM   — a single source emitting > SOURCE_TRIP events in WINDOW_MIN
  • GLOBAL FLOOD  — total events in WINDOW_MIN > GLOBAL_TRIP (system-wide loop)
  • RAM RUNAWAY   — RAM% over RAM_CEILING

On trip: stop the offending worker's systemd timer+service (never a PROTECTED
core unit), record it, and ALERT Andrew (critical — this one is meant to
interrupt). Cooldown prevents flapping.

Modes:
  --calibrate   report current rates so thresholds stay above normal (no action)
  --check       detect + log + alert, but DO NOT stop (safe default / dry-run)
  --arm         detect + actually STOP the offending non-core worker
"""
import sys, json, sqlite3, subprocess, argparse
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
DB = BASE / "memory/echo_events.db"
STATE = BASE / "memory/circuit_breaker_state.json"
LOG = BASE / "logs/circuit_breaker.log"

# ── thresholds (calibrated against real rates — see --calibrate) ─────────────
WINDOW_MIN   = 5
SOURCE_TRIP  = 120     # one source firing >120 events / 5min = looping (~24/min)
GLOBAL_TRIP  = 400     # >400 events / 5min system-wide = a flood
RAM_CEILING  = 93      # percent
COOLDOWN_MIN = 15

# Core units the breaker must NEVER stop (its own safety + the spine).
# Spine additions per Codex review #98: echo-core, echo-governor-v2, echo-conductor-agents.
PROTECTED = {
    "echo-core", "echo-core-state", "echo-core-state-writer", "echo-core-state-autofix",
    "echo-governor", "echo-governor-v2", "echo-heartbeat", "echo-watchdog",
    "echo-conductor-agents", "echo-conductor-agents-repair",
    "echo-claude-bus-watch", "echo-codex-bus-watch", "echo-circuit-breaker",
    "echo-telegram-intake",
}

# Sources whose unit name doesn't follow the 'echo-<source>' heuristic — verified
# against installed units (Codex review #98, which found 22/38 sources unmapped).
# None = no standalone stoppable unit (runs inside another process / library / manual);
# the breaker then alerts for MANUAL action instead of falsely claiming a stop.
SOURCE_UNIT_ALIASES = {
    "self_act":           "echo-self-act-worker",   # loudest emitter; heuristic missed it
    "initiative_engine":  "echo-initiative",
    "devto_analytics":    "echo-analytics",
    "content_pipeline":   "echo-content-gen",
    "regret_scorer":      None,   # runs inside echo-governor
    "notion_task_reader": None,   # runs inside echo-governor
    "alpaca_reconciler":  None,   # dispatcher/trading child, no standalone unit
    "weekly_reviewer":    None,
    "strategy_reviewer":  None,
    "draft_writer":       None,
    "interaction_ledger": None,
}

_installed_cache = None


def _installed_units():
    """Set of installed echo-* unit base names (so we never try to stop a phantom)."""
    global _installed_cache
    if _installed_cache is None:
        import re as _re
        r = subprocess.run(["systemctl", "--user", "list-unit-files", "echo-*", "--no-pager"],
                           capture_output=True, text=True)
        _installed_cache = set(_re.findall(r"(echo-[a-z0-9-]+)\.(?:timer|service)", r.stdout))
    return _installed_cache


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def _recent_rows(minutes):
    cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
    db = sqlite3.connect(str(DB), timeout=10)
    try:
        return db.execute(
            "SELECT ts, event_type, source FROM events WHERE ts >= ?", (cutoff,)
        ).fetchall()
    finally:
        db.close()


def _ram_pct():
    try:
        st = json.loads((BASE / "memory/echo_state.json").read_text())
        return float(st.get("system", {}).get("ram_pct") or 0)
    except Exception:
        return 0.0


def source_to_unit(source: str):
    """Resolve an event source to a STOPPABLE installed unit, or None.
    Explicit aliases first (Codex #98), then the 'echo-<source>' heuristic, then
    verify the unit is actually installed. None => no stoppable unit; the breaker
    alerts for manual action rather than pretending it stopped something."""
    src = (source or "").strip().lower()
    if src in SOURCE_UNIT_ALIASES:
        unit = SOURCE_UNIT_ALIASES[src]
    else:
        unit = "echo-" + src.replace("_", "-").replace(" ", "-")
    if unit and unit in _installed_units():
        return unit
    return None


def _load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {"trips": [], "last_trip_by_source": {}}


def _save_state(s):
    STATE.write_text(json.dumps(s, indent=2))


def _in_cooldown(state, source):
    last = state["last_trip_by_source"].get(source)
    if not last:
        return False
    return datetime.now() - datetime.fromisoformat(last) < timedelta(minutes=COOLDOWN_MIN)


def stop_unit(unit_base: str) -> bool:
    """Stop <unit>.timer + <unit>.service. Returns True if the stop ran."""
    if unit_base in PROTECTED:
        log(f"REFUSED to stop protected unit {unit_base}")
        return False
    ok = False
    for suffix in (".timer", ".service"):
        r = subprocess.run(["systemctl", "--user", "stop", unit_base + suffix],
                           capture_output=True, text=True)
        if r.returncode == 0:
            ok = True
    return ok


def alert(title, msg):
    try:
        from core.notifier import notify
        notify(title, msg, urgent=True, phone=True, desktop=True)
    except Exception as e:
        log(f"alert failed: {e}")


def calibrate():
    from collections import Counter
    rows = _recent_rows(WINDOW_MIN)
    by_src = Counter(r[2] for r in rows)
    print(f"window: last {WINDOW_MIN} min")
    print(f"total events: {len(rows)}  (GLOBAL_TRIP={GLOBAL_TRIP})")
    print(f"RAM: {_ram_pct():.0f}%  (RAM_CEILING={RAM_CEILING})")
    print(f"top sources (SOURCE_TRIP={SOURCE_TRIP}):")
    for src, n in by_src.most_common(10):
        flag = "  <-- would trip" if n > SOURCE_TRIP else ""
        print(f"  {src:24} {n:5}{flag}")


def run(arm: bool):
    from collections import Counter
    state = _load_state()
    rows = _recent_rows(WINDOW_MIN)
    by_src = Counter(r[2] for r in rows)
    total = len(rows)
    ram = _ram_pct()
    tripped = []

    # 1) per-source storm
    for src, n in by_src.items():
        if n > SOURCE_TRIP and not _in_cooldown(state, src):
            tripped.append(("event_storm", src, f"{n} events/{WINDOW_MIN}min"))

    # 2) global flood (act on the single loudest source if not already caught)
    if total > GLOBAL_TRIP:
        loud = by_src.most_common(1)[0][0] if by_src else "unknown"
        if not any(t[1] == loud for t in tripped) and not _in_cooldown(state, loud):
            tripped.append(("global_flood", loud, f"{total} events/{WINDOW_MIN}min total"))

    # 3) RAM runaway (no specific source — alert only, don't guess what to kill)
    if ram > RAM_CEILING:
        tripped.append(("ram_runaway", None, f"RAM {ram:.0f}% > {RAM_CEILING}%"))

    if not tripped:
        return 0

    for kind, src, detail in tripped:
        unit = source_to_unit(src) if src else None
        # Only auto-stop a clear single-source STORM — that's the unambiguous runaway
        # signature. Global floods + RAM runaways ALERT ONLY even when armed: on a busy
        # legit day we must not guess which worker to kill.
        can_stop = arm and unit and kind == "event_storm"
        if can_stop:
            stopped = stop_unit(unit)
            action = f"STOPPED {unit}" if stopped else f"could not stop {unit} (protected)"
        elif kind == "event_storm" and not unit:
            action = f"MANUAL INTERVENTION NEEDED — no stoppable unit for source '{src}' (runs inside another process/library)"
        elif arm:
            action = "ALERT-ONLY (flood/ram — won't guess which worker to kill)"
        else:
            action = "ALERT-ONLY (use --arm to stop storms)"
        log(f"TRIP [{kind}] source={src} {detail} -> {action}")
        alert(f"Circuit breaker: {kind}",
              f"{src or 'system'} — {detail}. {action}")
        if src:
            state["last_trip_by_source"][src] = datetime.now().isoformat()
        state["trips"].append({"ts": datetime.now().isoformat(), "kind": kind,
                               "source": src, "detail": detail, "armed": arm,
                               "action": action})
    state["trips"] = state["trips"][-100:]
    _save_state(state)
    return len(tripped)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--check", action="store_true", help="detect+alert, do NOT stop")
    ap.add_argument("--arm", action="store_true", help="detect AND stop offenders")
    a = ap.parse_args()
    if a.calibrate:
        calibrate()
    elif a.arm:
        n = run(arm=True); log(f"cycle done — {n} trips (armed)") if n else None
    else:  # --check default
        n = run(arm=False); log(f"cycle done — {n} trips (alert-only)") if n else None


if __name__ == "__main__":
    main()
