#!/usr/bin/env python3
import subprocess
import signal
import sys
from echo_utils import safe_print

# List of passive scripts
SCRIPTS = [
    "run_google_opinion_rewards.py",
    "run_passiveapp.py",
    "run_gamepayer.py"
]

processes = []

def terminate_all(signum, frame):
    safe_print("\n[All Passive] Terminating all passive streams...")
    for p in processes:
        p.terminate()
    for p in processes:
        p.wait()
    safe_print("[All Passive] All processes terminated.")
    sys.exit(0)

# Catch Ctrl+C / termination signals
signal.signal(signal.SIGINT, terminate_all)
signal.signal(signal.SIGTERM, terminate_all)

safe_print("[All Passive] Launching all passive income streams...")

# Launch all scripts
for script in SCRIPTS:
    p = subprocess.Popen([sys.executable, f"./{script}"], stdout=sys.stdout, stderr=sys.stderr)
    processes.append(p)

# Keep script alive until all subprocesses finish
try:
    for p in processes:
        p.wait()
except KeyboardInterrupt:
    terminate_all()
