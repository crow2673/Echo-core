#!/usr/bin/env python3
"""
Automate daily system health checks and log summaries, trigger on daily system startup, notify via ntfy if critical issues detected.
"""

import logging
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from core.notifier import notify

logging.basicConfig(filename=BASE / "logs" / "system_health.log", level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

def check_disk_usage():
    try:
        result = subprocess.run(['df', '-h', '/'], capture_output=True, text=True, check=True)
        logging.info(f"Disk usage: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error checking disk usage: {e.stderr}")

def check_memory_usage():
    try:
        result = subprocess.run(['free', '-h'], capture_output=True, text=True, check=True)
        logging.info(f"Memory usage: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error checking memory usage: {e.stderr}")

NOISE_PATTERNS = [
    "vastai_kaalia", "vast_metrics", "launch_metrics_pusher",
    "NetworkManager", "bluetoothd", "ModemManager",
]

def check_system_logs():
    try:
        result = subprocess.run(
            ['journalctl', '-p', 'err', '--since', '24h ago', '--no-pager', '-q'],
            capture_output=True, text=True
        )
        all_errors = [l for l in result.stdout.splitlines() if l.strip()]
        errors = [l for l in all_errors if not any(n in l for n in NOISE_PATTERNS)]
        if errors:
            summary = f"{len(errors)} errors in last 24h ({len(all_errors)-len(errors)} noise filtered)"
            logging.warning(summary + "\n" + "\n".join(errors[:5]))
            notify("System Log Errors", summary, urgent=True)
        else:
            logging.info(f"No real errors in last 24h ({len(all_errors)} noise lines filtered)")
    except Exception as e:
        logging.error(f"Error reading system logs: {e}")

def check_network_status():
    try:
        result = subprocess.run(['ping', '-c', '4', '8.8.8.8'], capture_output=True, text=True, check=True)
        logging.info(f"Network status: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error checking network status: {e.stderr}")
        notify("Network Error", "Failed to reach 8.8.8.8", urgent=True)

if __name__ == "__main__":
    check_disk_usage()
    check_memory_usage()
    check_system_logs()
    check_network_status()