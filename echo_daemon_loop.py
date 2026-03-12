#!/usr/bin/env python3
import os
import time
import subprocess

os.chdir('/home/andrew/Echo')

BOT_CMD = ['/home/andrew/Echo/venv/bin/python3', 'trading_bot.py', 'ramp']
AGENT_CMD = ['/home/andrew/Echo/venv/bin/python3', 'echo_simple_agent.py']
JARVIS_CMD = ['/home/andrew/Echo/venv/bin/python3', 'jarvis_voice.py']
SELF_CHECK_CMD = ['/home/andrew/Echo/venv/bin/python3', 'self_check.py']

bot_proc = None

def run_agent():
    subprocess.run(AGENT_CMD, timeout=600)

def ensure_bot_running():
    global bot_proc
    if bot_proc is None or bot_proc.poll() is not None:
        bot_proc = subprocess.Popen(BOT_CMD)
        print(f"✅ Started trading bot: pid={bot_proc.pid}")

def run_self_check():
    result = subprocess.run(SELF_CHECK_CMD, capture_output=True, text=True)
    print("Echo Self-Check Report:\n", result.stdout)

while True:
    try:
        print("∞ Daemon: Agent + Bot + Jarvis")
        ensure_bot_running()
        run_agent()

        now = int(time.time())

        # Jarvis voice roughly once an hour (first 5 minutes)
        if now % 3600 < 300:
            subprocess.run(JARVIS_CMD)
            print("🗣️ Jarvis GLM!")

        # Self-check every hour (first minute)
        if now % 3600 < 60:
            run_self_check()

        print("∞ Cycle OK")
    except Exception as e:
        print(f"Loop err: {e} - Retry")

    time.sleep(5)
