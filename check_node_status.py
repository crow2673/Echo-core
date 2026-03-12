#!/usr/bin/env python3
import subprocess

try:
    # Check provider offers through yagna
    offers = subprocess.check_output(['yagna', 'market', 'list-offers'], text=True)
    print("Current Offers:")
    print(offers)
except Exception as e:
    print(f"Error checking offers: {e}")

try:
    payments = subprocess.check_output(['yagna', 'payment', 'status'], text=True)
    print("\nPayment Status:")
    print(payments)
except Exception as e:
    print(f"Error checking payment status: {e}")

try:
    logs = subprocess.check_output(['journalctl', '--user', '-u', 'golem-provider.service', '--lines=20'], text=True)
    print("\nRecent Logs (golem-provider):")
    print(logs)
except Exception as e:
    print(f"Error reading provider logs: {e}")
