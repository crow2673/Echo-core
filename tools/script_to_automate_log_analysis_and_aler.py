#!/usr/bin/env python3
"""
Scan Echo's log files for new ERROR/CRITICAL lines since last run and alert via Telegram.
Uses a state file to track byte offsets so only new content is checked each run.
"""

import re
import json
import logging
from pathlib import Path
from datetime import datetime
import sys

BASE = Path(__file__).resolve().parents[1]
LOG_FILE = BASE / 'logs' / 'log_analysis.log'
STATE_FILE = BASE / 'memory' / 'log_analysis_state.json'

logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s %(message)s')

sys.path.insert(0, str(BASE))
from core.notifier import notify

# Match lines that are actual ERROR or CRITICAL log entries (standard logging format)
ALERT_PATTERN = re.compile(r'\b(ERROR|CRITICAL)\b')

# Logs to skip — either meta files or this script's own output
SKIP_LOGS = {'log_analysis.log', 'daemon.log'}


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state):
    tmp = STATE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(STATE_FILE)


def scan_new_lines(log_file, last_offset):
    """Read only bytes past last_offset. Return (new_alerts, new_offset)."""
    alerts = []
    try:
        size = log_file.stat().st_size
        if size <= last_offset:
            return [], last_offset  # no new content
        with log_file.open('rb') as f:
            f.seek(last_offset)
            new_bytes = f.read()
        new_text = new_bytes.decode('utf-8', errors='replace')
        for line in new_text.splitlines():
            if ALERT_PATTERN.search(line):
                alerts.append(line.strip()[:200])
        return alerts, size
    except Exception as e:
        logging.error(f"scan error {log_file.name}: {e}")
        return [], last_offset


def main():
    log_dir = BASE / 'logs'
    log_files = [f for f in log_dir.glob('*.log') if f.name not in SKIP_LOGS]

    state = load_state()
    all_alerts = []

    for log_file in sorted(log_files):
        key = log_file.name
        last_offset = state.get(key, 0)
        new_alerts, new_offset = scan_new_lines(log_file, last_offset)
        state[key] = new_offset
        for line in new_alerts:
            all_alerts.append(f"[{log_file.stem}] {line}")

    save_state(state)

    if all_alerts:
        # Cap to 10 alerts per run to avoid Telegram spam
        summary = '\n'.join(all_alerts[:10])
        if len(all_alerts) > 10:
            summary += f'\n... and {len(all_alerts) - 10} more'
        notify("Echo Log Alerts", summary, urgent=True)
        logging.info(f"Alerted on {len(all_alerts)} new ERROR/CRITICAL lines")
    else:
        logging.info("No new errors found")


if __name__ == "__main__":
    main()
