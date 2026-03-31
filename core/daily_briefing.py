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
    except Exception as _e:
        cpu = '?'; ram_used = '?'; swap_line = 'Swap: ?'; gpu = '?'
        system_health = 'unknown'; positions_open = 0; regret_status = 'unknown'
        session_context = 'State file unavailable.'
    briefing_prompt = (
        f"{greeting} Andrew. Today is {day}. "
        f"Weather: {weather_line}. "
        f"LIVE SYSTEM — CPU: {cpu}%, RAM: {ram_used}, {swap_line}, GPU: {gpu}. Health: {system_health}. "
        f"Trading: {positions_open} positions open. Regret index: {regret_status}. "
        f"1) Current system and service status using the real stats above. "
        f"2) Golem node earnings and task status. "
        f"3) Build context: {session_context} "
        f"4) The single most important thing to work on today to move toward income. "
        f"Keep it concise and spoken — read aloud. No follow-up questions. End with a complete thought."
    )

    result = subprocess.run(
        ["python3", str(INTAKE), "--text", briefing_prompt],
        capture_output=True, text=True
    )
    print(result.stdout.strip())
    print(result.stderr.strip())

    # Wait for reply then speak it
    import time
    cap_id = result.stdout.strip().split("queued ")[-1] if "queued" in result.stdout else None
    print(f"Waiting for Echo to process briefing...")
    for _ in range(24):  # wait up to 4 minutes
        time.sleep(10)
        try:
            m = json.load(open(BASE_DIR / "echo_memory.json"))
            found = False
            for c in m:
                if found and c.get("type") == "reply":
                    text = c.get("text", "")
                    if text:
                        print(f"[briefing] Speaking: {text[:100]}...")
                        with open(Path.home() / "Echo/logs/briefing_transcript.log", "a") as f:
                            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} — {text}\n")
                        from echo_voice import speak
                        speak(text)
                    return
                if c.get("type") == "message" and "daily briefing" in c.get("text", ""):
                    found = True
        except Exception as e:
            print(f"check error: {e}")
    print("[briefing] Timed out waiting for reply")

if __name__ == "__main__":
    queue_briefing()