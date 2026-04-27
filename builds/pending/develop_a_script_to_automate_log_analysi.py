#!/usr/bin/env python3
"""
Automate log analysis and alert generation for critical errors.
"""

import os
import logging
from pathlib import Path
import psutil
import sys

BASE = Path(__file__).resolve().parents[1]
LOG_FILE = BASE / 'logs' / 'log_analysis.log'

logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s %(message)s")

env_file = Path.home() / ".config/echo/golem.env"
ENV = {}
for line in env_file.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1)
        ENV[k] = v

sys.path.insert(0, str(BASE))
from core.notifier import notify

def analyze_logs(log_path):
    critical_keywords = ['CRITICAL', 'ERROR', 'FATAL']
    alerts = []
    try:
        logs = log_path.read_text()
        for line in logs.splitlines():
            if any(keyword in line for keyword in critical_keywords):
                alerts.append(line)
    except Exception as e:
        logging.error(f"Error reading logs: {e}")
    return alerts

def generate_alerts(alerts):
    for alert in alerts:
        logging.warning(f"Critical alert: {alert}")
        notify("Critical Error Alert", alert, urgent=True)

def check_system_resources():
    cpu_usage = psutil.cpu_percent(interval=2)
    ram_usage = psutil.virtual_memory().percent
    disk_usage = psutil.disk_usage(str(Path.home())).percent
    logging.info(f"System Resources: CPU {cpu_usage}%, RAM {ram_usage}%, Disk {disk_usage}%")

def main():
    memory_path = BASE / 'memory'
    log_files = list(memory_path.glob('*.log'))
    for log_file in log_files:
        alerts = analyze_logs(log_file)
        if alerts:
            generate_alerts(alerts)
    check_system_resources()

if __name__ == "__main__":
    main()