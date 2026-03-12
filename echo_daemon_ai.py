#!/usr/bin/env python3
import os
import time
import subprocess
from datetime import datetime

BASE = "/home/andrew/Echo"
os.chdir(BASE)

PY = "/usr/bin/python3"  # use system python; echo_agi_lite.py doesn't need venv
# If you prefer venv python, swap to: PY = f"{BASE}/venv/bin/python3"

def run_forever(cmd, name):
    # Runs command; if it exits, restart after short delay
    while True:
        print(f"[{datetime.now().isoformat(timespec='seconds')}] START {name}: {' '.join(cmd)}")
        try:
            p = subprocess.Popen(cmd)
            rc = p.wait()
            print(f"[{datetime.now().isoformat(timespec='seconds')}] EXIT {name}: rc={rc}")
        except Exception as e:
            print(f"[{datetime.now().isoformat(timespec='seconds')}] ERR {name}: {e}")
        time.sleep(3)

def hourly_task(last_ts, fn):
    now = time.time()
    if now - last_ts >= 3600:
        fn()
        return now
    return last_ts

def do_self_check():
    subprocess.run([PY, "self_check_ai.py"])

def main():
    # optional: ensure log file exists
    open("echo_activity.log", "a").close()

    last_check = 0

    # Start echo_agi_lite in a child process that we supervise
    # (We keep main loop free for periodic tasks)
    agi = subprocess.Popen([PY, "echo_agi_lite.py"])

    print(f"[{datetime.now().isoformat(timespec='seconds')}] AI daemon running (agi pid={agi.pid})")

    while True:
        # Restart if echo_agi_lite died
        if agi.poll() is not None:
            print(f"[{datetime.now().isoformat(timespec='seconds')}] echo_agi_lite died; restarting")
            agi = subprocess.Popen([PY, "echo_agi_lite.py"])

        last_check = hourly_task(last_check, do_self_check)
        time.sleep(5)

if __name__ == "__main__":
    main()
