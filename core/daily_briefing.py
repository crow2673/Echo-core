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

    import psutil, subprocess
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    ram_used = f"{ram.used / 1024**3:.1f}GB of {ram.total / 1024**3:.1f}GB ({ram.percent}%)"
    swap = psutil.swap_memory()
    swap_line = f"Swap: {swap.used / 1024**3:.1f}GB of {swap.total / 1024**3:.1f}GB used" if swap.used > 0 else "Swap: clear"
    try:
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    except:
        gpu = "unavailable"

    try:
        changelog_lines = (BASE / "CHANGELOG.md").read_text().strip().splitlines()
        changelog_snippet = "\n".join(changelog_lines[-30:])
    except:
        changelog_snippet = "unavailable"
    try:
        todo = (BASE / "TODO.md").read_text().strip()
    except:
        todo = "unavailable"
    briefing_prompt = (
        f"{greeting} Andrew. Today is {day}. "
        f"Give me a full daily briefing covering: "
        f"Weather today: {weather_line}. "
        f"REAL SYSTEM STATS RIGHT NOW — CPU: {cpu}%, RAM: {ram_used}, {swap_line}, GPU: {gpu}. "
        f"1) Current system and service status using the real stats above. "
        f"2) Golem node earnings and task status. "
        f"3) What we were building last session and where we left off — recent CHANGELOG: {changelog_snippet}. "
        f"Current TODO list: {todo}. 4) Given the TODO list, what is the single most important thing to work on today. "
        f"Keep it concise and spoken — this will be read aloud. Do not offer to continue or ask follow up questions. End with a complete thought."
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
