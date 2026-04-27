#!/usr/bin/env python3
"""
Automate log analysis and alert generation based on predefined patterns.
"""

import os
import re
import psutil
import logging
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]

# Logging setup
log_path = BASE / 'logs' / 'log_analysis.log'
logging.basicConfig(filename=log_path, level=logging.INFO, format='%(asctime)s %(message)s')

# Import notify function
sys.path.insert(0, str(BASE))
from core.notifier import notify

# Environment variables
env_file = Path.home() / ".config/echo/golem.env"
ENV = {}
for line in env_file.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1)
        ENV[k] = v

# Predefined patterns
PATTERNS = {
    'error': re.compile(r'error', re.IGNORECASE),
    'warning': re.compile(r'warning', re.IGNORECASE),
    'critical': re.compile(r'critical', re.IGNORECASE),
}

def analyze_logs(log_files):
    """Analyze log files for predefined patterns and generate alerts."""
    alerts = []
    for log_file in log_files:
        try:
            log_content = log_file.read_text()
            for pattern_name, pattern in PATTERNS.items():
                if pattern.search(log_content):
                    alerts.append((log_file.name, pattern_name))
        except Exception as e:
            logging.error(f"Failed to read {log_file}: {e}")
    return alerts

def main():
    """Main function to run log analysis."""
    try:
        # Check system resource usage
        cpu_usage = psutil.cpu_percent(interval=2)
        ram_usage = psutil.virtual_memory().percent
        if cpu_usage > 80 or ram_usage > 80:
            notify("Resource Alert", f"High resource usage detected: CPU {cpu_usage}%, RAM {ram_usage}%.", urgent=True)

        # Log files to analyze
        log_dir = BASE / 'memory'
        log_files = list(log_dir.glob('*.log'))

        # Analyze logs
        alerts = analyze_logs(log_files)
        if alerts:
            for log_file, pattern in alerts:
                notify(f"Log Alert: {pattern}", f"Pattern '{pattern}' detected in {log_file}.", urgent=True)
    except Exception as e:
        logging.error(f"Error in main function: {e}")
        notify("Error in Log Analysis Script", str(e), urgent=True)

if __name__ == "__main__":
    main()