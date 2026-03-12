#!/usr/bin/env python3
import time
from echo_utils import safe_print

# Placeholder for starting balance (replace with actual API call)
balance = 0.0
count = 0

safe_print("[Google Opinion Rewards] Starting task loop...")

try:
    while True:
        count += 1

        # --- Placeholder for real task ---
        # TODO: integrate Google Opinion Rewards automation
        earned = 0.50  # Example: points converted to $ (replace with actual API)
        balance += earned

        safe_print(f"[Google Opinion Rewards] Task #{count} executed. Earned ${earned:.2f}. Current balance: ${balance:.2f}")

        time.sleep(30)  # adjust as needed
except KeyboardInterrupt:
    safe_print(f"[Google Opinion Rewards] Stopped by user. Final balance: ${balance:.2f}")
