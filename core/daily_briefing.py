#!/usr/bin/env python3
"""
daily_briefing.py
Echo generates and speaks a daily briefing automatically.
Covers: system status, income status, pending tasks, what to build today.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LOG = BASE / "logs/briefing_transcript.log"


def _load_mission_context():
    changelog = Path.home() / "Echo/CHANGELOG.md"
    if changelog.exists():
        lines = changelog.read_text().splitlines()
        recent = [l for l in lines if l.strip()][:20]
        return "\nCURRENT BUILD STATUS (from CHANGELOG):\n" + "\n".join(recent)
    return ""


def queue_briefing():
    now = datetime.now()
    hour = now.hour
    greeting = "Good morning" if hour < 12 else ("Good evening" if hour >= 18 else "Good afternoon")
    date_str = now.strftime("%A, %B %d")

    try:
        from core.weather import get_weather
        weather = get_weather()
        weather_str = weather.get("summary", "?")
    except Exception:
        weather_str = "?"

    # Load system state
    system_str = "unknown"
    trading_str = "unknown"
    health_str = "unknown"
    session_focus = "Last build focus not confirmed from state."
    next_priority = ""

    try:
        state_file = Path.home() / "Echo/memory/echo_state.json"
        if state_file.exists():
            state = json.loads(state_file.read_text())
            sys_info = state.get("system", {})
            cpu = sys_info.get("cpu_pct", "?")
            ram = sys_info.get("ram_pct", "?")
            ram_used = sys_info.get("ram_used_gb", "?")
            ram_total = sys_info.get("ram_total_gb", "?")
            swap = sys_info.get("swap_used_gb", 0)
            gpu = sys_info.get("gpu_pct", "?")
            vram = sys_info.get("vram_used_mb", "?")
            health_str = state.get("system_health", "unknown")

            system_str = f"CPU: {cpu}%, RAM: {ram_used}GB of {ram_total}GB ({ram}%)"
            if vram and vram != "?":
                system_str += f", GPU: {gpu}%, VRAM: {vram}MB"
            if swap and float(swap) > 1:
                system_str += f", Swap: {swap}GB used"

            income = state.get("income", {})
            positions = income.get("positions_open", "?")
            trading_str = f"{positions} positions open"

            session_ctx = state.get("session_context", {})
            session_focus = session_ctx.get("session_focus", session_focus)
            next_priority = session_ctx.get("next_priority", "")
    except Exception:
        pass

    # Cascade P/L
    cascade_str = ""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("cascade_ledger", BASE / "core/cascade_ledger.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ledger = mod.load_ledger()
        total_pl = sum(v.get("realized_pl", 0) for v in ledger.values())
        cascade_str = f"Cascade realized P/L: ${total_pl:+.0f} total."
    except Exception:
        pass

    mission = _load_mission_context()

    prompt = (
        f"{greeting} Andrew. Today is {date_str}. Weather: {weather_str}. "
        f"LIVE SYSTEM — CPU: {system_str}. Health: {health_str}. "
        f"Trading: {trading_str}."
    )
    if cascade_str:
        prompt += f" {cascade_str}"
    if next_priority:
        prompt += f" Next: {next_priority}."
    prompt += (
        f" {session_focus} Andrew. Today is {date_str}. Weather: {weather_str}."
        f" LIVE SYSTEM — CPU: {system_str}. Health: {health_str}."
        f" Trading: {trading_str}."
    )
    prompt += (
        " . Speak this as a short morning briefing — 4 sentences max. "
        "Cover: system health, trading positions, and the one most important thing to do today. "
        "Be direct. No lists."
    )
    if mission:
        prompt += mission

    print("[briefing] Calling Ollama directly...", flush=True)
    try:
        from core.providers.router import call_ollama
        # Warm up model
        try:
            call_ollama("hi", model="qwen2.5:32b", timeout=30)
            print("[briefing] Model warmed up", flush=True)
        except Exception as e:
            print(f"[briefing] Warmup skipped: {e}", flush=True)

        response = call_ollama(prompt, model="qwen2.5:32b", timeout=120)
        if not response:
            raise ValueError("empty response")
        print(f"[briefing] Generated: {response[:80]}...", flush=True)

        # Log transcript
        LOG.parent.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG, "a") as f:
            f.write(f"{ts} — {response}\n")

        # Speak via notifier
        try:
            from core.notifier import notify
            notify("Echo Daily Briefing", response, urgent=False)
            print("[briefing] Spoken successfully", flush=True)
        except Exception as e:
            print(f"[briefing] speak error: {e}", flush=True)

        try:
            from core.event_ledger import log_event
            log_event("system", "daily_briefing", response[:120], score=1.0)
        except Exception:
            pass

    except Exception as e:
        print(f"[briefing] Failed to generate briefing: {e}", flush=True)


if __name__ == "__main__":
    queue_briefing()
