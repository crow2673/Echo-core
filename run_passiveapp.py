#!/usr/bin/env python3
import time
from echo_utils import safe_print

balance = 0.0
count = 0

safe_print("[PassiveApp] Starting task loop...")

try:
    while True:
        count += 1

        # --- Placeholder for real task ---
        earned = 0.30  # Example: replace with actual earnings
        balance += earned

        safe_print(f"[PassiveApp] Task #{count} executed. Earned ${earned:.2f}. Current balance: ${balance:.2f}")

        time.sleep(30)
except KeyboardInterrupt:
    safe_print(f"[PassiveApp] Stopped by user. Final balance: ${balance:.2f}")
