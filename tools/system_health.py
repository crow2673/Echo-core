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

def check_system_logs():
    try:
        result = subprocess.run(
            ['journalctl', '-p', 'err', '--since', '24h ago', '--no-pager', '-q'],
            capture_output=True, text=True
        )
        errors = [l for l in result.stdout.splitlines() if l.strip()]
        if errors:
            summary = f"{len(errors)} system errors in last 24h"
            logging.warning(summary + "\n" + "\n".join(errors[:5]))
            notify("System Log Errors", summary, urgent=True)
        else:
            logging.info("No system errors in last 24h")
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