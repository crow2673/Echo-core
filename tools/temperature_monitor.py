#!/usr/bin/env python3
"""
Monitor system temperature and trigger a notification if it exceeds 70°C.
"""

import sys
import logging
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

# Set up logging
logging.basicConfig(filename=BASE / 'logs' / 'temperature_monitor.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def get_system_temperature():
    try:
        result = subprocess.run(['sensors'], capture_output=True, text=True, check=True)
        for line in result.stdout.split('\n'):
            if 'Core 0' in line:
                temp = float(line.split()[2][1:])
                return temp
    except Exception as e:
        logging.error(f"Error fetching system temperature: {e}")
    return None

def notify_if_high_temperature(temperature):
    try:
        from core.notifier import notify
        if temperature > 70:
            notify('High Temperature Alert', f'System temperature is {temperature}°C')
    except Exception as e:
        logging.error(f"Error sending notification: {e}")

def main():
    temperature = get_system_temperature()
    if temperature is not None:
        logging.info(f"Current system temperature: {temperature}°C")
        notify_if_high_temperature(temperature)
    else:
        logging.info("Temperature unavailable (sensors not installed?)")

if __name__ == "__main__":
    main()