#!/usr/bin/env python3
"""
core/echo_now.py — a glanceable "what is Echo doing right now" snapshot.

Andrew asked Echo "how do I know when you're working?" — this answers it: her
current health, whether she's actively thinking (a model loaded in ollama),
what she did most recently, and her latest thought. Exposed as the /status
Telegram command and runnable directly.

Usage:
  python3 -m core.echo_now
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
STATE = BASE / "memory" / "echo_state.json"
EXPERIENCE = BASE / "memory" / "experience_log.jsonl"
INNER = BASE / "logs" / "inner_voice.log"
NARRATIVE = BASE / "memory" / "life_narrative.md"
LIFE_LOOP = BASE / "memory" / "life_loop_state.json"


def _is_thinking() -> str:
    """A model loaded in ollama means she's actively reasoning right now."""
    try:
        out = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=6).stdout
        lines = [l for l in out.splitlines()[1:] if l.strip()]
        if lines:
            model = lines[0].split()[0]
            return f"🟢 thinking now (model {model} loaded)"
        return "⚪ idle (no model loaded — not mid-thought)"
    except Exception:
        return "⚪ idle"


def _recent_actions(n=4):
    if not EXPERIENCE.exists():
        return []
    out = []
    for ln in EXPERIENCE.read_text(errors="ignore").splitlines()[-200:]:
        try:
            e = json.loads(ln)
        except Exception:
            continue
        if e.get("type") == "heartbeat":
            continue
        ts = (e.get("ts", "") or "")[11:19]
        what = e.get("summary") or e.get("type") or "?"
        out.append(f"{ts} {str(what)[:70]}")
    return out[-n:]


def _recent_timers(state, n=5):
    fresh = []
    for name, t in (state.get("timers") or {}).items():
        if isinstance(t, dict) and t.get("age_seconds") is not None:
            fresh.append((t["age_seconds"], name))
    fresh.sort()
    return [name.replace("echo-", "") for _, name in fresh[:n]]


def _last_thought():
    if not INNER.exists():
        return ""
    for ln in reversed(INNER.read_text(errors="ignore").splitlines()):
        if ln.strip() and "entry written" not in ln and "] starting" not in ln:
            return ln.strip()[:160]
    return ""


def _life_priority():
    if not LIFE_LOOP.exists():
        return ""
    try:
        state = json.loads(LIFE_LOOP.read_text())
        priority = state.get("current_priority", {})
        title = priority.get("title", "")
        next_step = priority.get("next_step", "")
        if title and next_step:
            return f"{title} -> {next_step}"
        return title
    except Exception:
        return ""


def snapshot() -> str:
    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text())
        except Exception:
            pass

    age = "?"
    if state.get("timestamp"):
        try:
            delta = datetime.now(timezone.utc) - datetime.fromisoformat(state["timestamp"])
            age = f"{int(delta.total_seconds())}s ago"
        except Exception:
            pass

    failed = (state.get("failed_units") or {}).get("units", [])
    lines = [
        "🧠 Echo — right now",
        f"health: {state.get('system_health', '?')} (state {age})",
        _is_thinking(),
    ]
    if failed:
        lines.append(f"⚠️ failed: {', '.join(failed)}")
    actions = _recent_actions()
    if actions:
        lines.append("recent:")
        lines += [f"  • {a}" for a in actions]
    timers = _recent_timers(state)
    if timers:
        lines.append("active loops: " + ", ".join(timers))
    life_priority = _life_priority()
    if life_priority:
        lines.append(f"life priority: {life_priority[:180]}")
    thought = _last_thought()
    if thought:
        lines.append(f"last thought: {thought}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(snapshot())
