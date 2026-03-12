import json
import time
import subprocess
import os
from pathlib import Path
from datetime import datetime
import signal
import sys

# Paths
BASE_DIR = Path.home() / "Echo"
PID_FILE = BASE_DIR / "echo_always_on.pid"
CONFIG_FILE = BASE_DIR / "loop_config.json"
LOG_FILE = BASE_DIR / "always_on_log.json"
AUTONOMOUS_TASK = BASE_DIR / "echo_autonomous_task.py"

# -------- SINGLE INSTANCE GUARD --------
def is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

if PID_FILE.exists():
    try:
        existing_pid = int(PID_FILE.read_text().strip())
        if is_process_running(existing_pid):
            print(f"Echo already running with PID {existing_pid}. Exiting.")
            sys.exit(0)
        else:
            PID_FILE.unlink()
    except Exception:
        PID_FILE.unlink()

PID_FILE.write_text(str(os.getpid()))

def cleanup_and_exit(signum=None, frame=None):
    if PID_FILE.exists():
        PID_FILE.unlink()
    print("Echo shutting down cleanly.")
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup_and_exit)
signal.signal(signal.SIGINT, cleanup_and_exit)

# -------- LOAD CONFIG --------
with open(CONFIG_FILE) as f:
    config = json.load(f)

interval = config.get("loop_interval_seconds", 60)

# Ensure log exists
if not LOG_FILE.exists():
    LOG_FILE.write_text("[]")

print(f"Echo always-on loop starting (PID {os.getpid()}) interval={interval}s")

# -------- MAIN LOOP --------
while True:
    timestamp = datetime.now().isoformat()

    heartbeat = {
        "timestamp": timestamp,
        "status": "Echo loop alive"
    }

    with open(LOG_FILE, "r+") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = []
        data.append(heartbeat)
        f.seek(0)
        json.dump(data, f, indent=2)
        f.truncate()

    print(f"[{timestamp}] Heartbeat logged.")

    result = subprocess.run(
        ["python3", str(AUTONOMOUS_TASK)],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(f"[{timestamp}] Autonomous task executed successfully.")
    else:
        print(f"[{timestamp}] Autonomous task ERROR:\n{result.stderr}")

    time.sleep(interval)
