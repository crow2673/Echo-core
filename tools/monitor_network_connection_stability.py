#!/usr/bin/env python3
"""
Monitor network connection stability.
"""

import psutil
import logging
import sys
import os
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parents[1]
LOG_FILE = BASE / "logs" / "network_monitor.log"
MEMORY_FILE = BASE / "memory" / "network_status.txt"

# Setup logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s %(message)s")

# Add notifier
sys.path.insert(0, str(BASE))
from core.notifier import notify

def check_network_connection():
    try:
        # Check network connection by pinging Google's DNS server
        response = subprocess.run(['ping', '-c', '1', '8.8.8.8'], stdout=subprocess.PIPE)
        if response.returncode == 0:
            return True
        else:
            return False
    except Exception as e:
        logging.error(f"Error checking network connection: {e}")
        return False

def main():
    try:
        if not check_network_connection():
            logging.warning("Network connection lost.")
            notify("Network Alert", "The network connection has been lost.", urgent=True)
            status = "Disconnected"
        else:
            logging.info("Network connection is stable.")
            status = "Connected"

        # Atomic write to memory file
        tmp_path = MEMORY_FILE.with_suffix('.tmp')
        tmp_path.write_text(status)
        tmp_path.rename(MEMORY_FILE)

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        notify("Network Monitor Error", f"An error occurred while monitoring network: {e}", urgent=True)

if __name__ == "__main__":
    main()