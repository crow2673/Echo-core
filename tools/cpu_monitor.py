#!/usr/bin/env python3
"""
Monitors CPU usage during off-peak hours and alerts if usage is high.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
LOG_FILE = BASE / "logs" / "cpu_monitor.log"
OFF_PEAK_START = 22  # 10pm
OFF_PEAK_END = 6    # 6am

logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

sys.path.insert(0, str(BASE))

def get_cpu_usage():
    try:
        import psutil
        return psutil.cpu_percent(interval=2)
    except ImportError:
        import subprocess
        result = subprocess.run(['top', '-bn1'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if '%Cpu' in line or 'Cpu(s)' in line:
                parts = line.replace(',', ' ').split()
                for i, p in enumerate(parts):
                    if 'id' in p and i > 0:
                        return round(100 - float(parts[i-1]), 1)
    return None

def is_off_peak():
    h = datetime.now().hour
    return h >= OFF_PEAK_START or h < OFF_PEAK_END

def main():
    if not is_off_peak():
        logging.info("Not during off-peak hours.")
        return

    cpu_usage = get_cpu_usage()
    if cpu_usage is None:
        logging.warning("Failed to fetch CPU usage.")
        return

    logging.info(f"Current CPU usage: {cpu_usage}%")

    if cpu_usage > 80:
        logging.warning(f"High CPU usage detected: {cpu_usage}%")
        try:
            from core.notifier import notify
            notify("High CPU Usage", f"CPU at {cpu_usage}% during off-peak hours", urgent=True)
        except Exception as e:
            logging.error(f"Failed to notify: {e}")

if __name__ == "__main__":
    main()
