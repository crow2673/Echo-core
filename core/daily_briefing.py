#!/usr/bin/env python3
"""
daily_briefing.py
Echo generates and speaks a daily briefing automatically.
Covers: system status, income status, pending tasks, what to build today.
"""
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

BASE = Path(__file__).resolve().parents[1]
MEMORY_FILE = BASE / "echo_memory.json"
INTAKE = BASE / "echo_message_intake.py"

def queue_briefing():
    from core.weather import get_weather
    wx = get_weather()
    weather_line = f"{wx['summary']}. {wx['advice']}"
    now = datetime.now()
    greeting = "Good morning" if now.hour < 12 else "Good evening" if now.hour >= 18 else "Good afternoon"
    day = now.strftime("%A, %B %d")

    # Load live system state from governor_v2 — single source of truth
    try:
        import json as _json
        _state = _json.loads(Path.home().joinpath('Echo/memory/echo_state.json').read_text())
        _sys = _state.get('system', {})
        cpu = _sys.get('cpu_pct', '?')
        ram_pct = _sys.get('ram_pct', '?')
        ram_used_gb = _sys.get('ram_used_gb', '?')
        ram_total_gb = _sys.get('ram_total_gb', '?')
        swap_used = _sys.get('swap_used_gb', 0)
        gpu_pct = _sys.get('gpu_pct', '?')
        vram_used = _sys.get('vram_used_mb', '?')
        system_health = _state.get('system_health', 'unknown')
        positions_open = _state.get('income', {}).get('positions_open', 0)
        regret_status = _state.get('regret_index', {}).get('status', 'unknown')
        ram_used = f'{ram_used_gb}GB of {ram_total_gb}GB ({ram_pct}%)'
        swap_line = f'Swap: {swap_used}GB used' if swap_used and float(str(swap_used)) > 0 else 'Swap: clear'
        gpu = f'{gpu_pct}%, VRAM: {vram_used}MB'
        _sc = _state.get('session_context', {})
        session_context = _sc.get('session_focus', 'Last build focus not confirmed from state.')
        next_priority = _sc.get('next_priority', '')
        if next_priority:
            session_context += f' Next: {next_priority}'
        # Add cascade sleeve summary
        try:
            import importlib.util as _ilu2
            _base2 = Path.home() / "Echo"
            _spec2 = _ilu2.spec_from_file_location("cascade_ledger", _base2 / "core/cascade_ledger.py")
            _mod2 = _ilu2.module_from_spec(_spec2)
            _spec2.loader.exec_module(_mod2)
            _ledger = _mod2.load_ledger()
            _total_pl = sum(_ledger[str(i)]["realized_pl"] for i in range(1, 5))
            cascade_line = f"Cascade realized P/L: ${_total_pl:+.0f} total."
        except Exception:
            cascade_line = ""
    except Exception as _e:
        cpu = '?'; ram_used = '?'; swap_line = 'Swap: ?'; gpu = '?'
        system_health = 'unknown'; positions_open = 0; regret_status = 'unknown'
        session_context = 'State file unavailable.'
    briefing_prompt = (
        f"{greeting} Andrew. Today is {day}. "
        f"Weather: {weather_line}. "
        f"LIVE SYSTEM — CPU: {cpu}%, RAM: {ram_used}, {swap_line}, GPU: {gpu}. Health: {system_health}. "
        f"Trading: {positions_open} positions open. Regret index: {regret_status}. "
        f"Speak this as a short morning briefing — 4 sentences max. Cover: system health, trading positions ({cascade_line}), and the one most important thing to do today. Be direct. No lists."
    )

    # Direct Ollama call — no daemon queue, no timeout dependency
    print("[briefing] Calling Ollama directly...")
    import urllib.request as _urllib
    import time as _time
    payload = json.dumps({
        "model": "qwen2.5:32b",
        "prompt": briefing_prompt,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 500}
    }).encode()
    briefing_text = None
    # Warmup ping to ensure model is loaded
    try:
        _ping = json.dumps({"model":"qwen2.5:32b","prompt":"hi","stream":False,"options":{"num_predict":1}}).encode()
        _preq = _urllib.Request("http://localhost:11434/api/generate", data=_ping, headers={"Content-Type":"application/json"}, method="POST")
        with _urllib.urlopen(_preq, timeout=60) as _pr: _pr.read()
        print("[briefing] Model warmed up")
    except Exception as _pe:
        print(f"[briefing] Warmup skipped: {_pe}")
    try:
        req = _urllib.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with _urllib.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
            briefing_text = data.get("response", "").strip()
    except Exception as e:
        print(f"[briefing] Ollama error: {e}")
        briefing_text = None
    if briefing_text:
        print(f"[briefing] Generated: {briefing_text[:100]}...")
        with open(Path.home() / "Echo/logs/briefing_transcript.log", "a") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} — {briefing_text}\n")
        try:
            from echo_voice import speak
            speak(briefing_text)
            print("[briefing] Spoken successfully")
        except Exception as e:
            print(f"[briefing] speak error: {e}")
    else:
        print("[briefing] Failed to generate briefing")

if __name__ == "__main__":
    queue_briefing()