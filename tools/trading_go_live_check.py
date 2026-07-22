#!/usr/bin/env python3
"""tools/trading_go_live_check.py — confirm the $10 live test is safe to run.

The ONLY income channel that's fully automatable (no captcha/bot walls) is
trading. This verifies the dedicated live keys are present, valid, and the
account is funded — WITHOUT moving any money. Run after adding ALPACA_LIVE_* to
golem.env; if all checks pass, the $10 experiment will trade real money on that
account ONLY (the main system stays on paper).

Run: python3 tools/trading_go_live_check.py
"""
import urllib.request, json, sys
from pathlib import Path

env = {}
for line in (Path.home() / ".config/echo/golem.env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

key = env.get("ALPACA_LIVE_API_KEY", "")
sec = env.get("ALPACA_LIVE_SECRET_KEY", "")
base = env.get("ALPACA_LIVE_BASE_URL", "https://api.alpaca.markets")

print("=" * 56)
print("  $10 LIVE TRADING — GO/NO-GO CHECK")
print("=" * 56)

checks = []

# 1. keys present
present = bool(key and sec)
checks.append(("Live keys present (ALPACA_LIVE_*)", present,
               "add ALPACA_LIVE_API_KEY + ALPACA_LIVE_SECRET_KEY to golem.env"))

# 2. key is a LIVE key (AK), not paper (PK)
is_live_key = key.startswith("AK")
checks.append(("Key is a LIVE key (starts with AK)", is_live_key,
               f"got prefix '{key[:2]}' — paper keys (PK) won't trade real money"))

acct = None
if present and is_live_key:
    try:
        req = urllib.request.Request(base + "/v2/account",
                                     headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        acct = json.load(urllib.request.urlopen(req, timeout=10))
    except Exception as e:
        checks.append(("Account reachable", False, str(e)))

if acct:
    checks.append(("Account reachable + active", acct.get("status") == "ACTIVE",
                   f"status={acct.get('status')}"))
    cash = float(acct.get("cash", 0))
    checks.append((f"Account funded (cash ${cash:.2f} >= $10)", cash >= 10,
                   "deposit at least $10 so the experiment has capital"))
    is_cash_acct = acct.get("account_blocked") is False
    checks.append(("Not blocked", not acct.get("account_blocked", False), ""))

allpass = all(ok for _, ok, _ in checks)
for name, ok, hint in checks:
    print(f"  [{'✓' if ok else '✗'}] {name}")
    if not ok and hint:
        print(f"       → {hint}")

print("-" * 56)
if allpass:
    print("  ✅ GO — the $10 experiment will trade REAL money on this account.")
    print("     Start it:  python3 core/experiment_10usd.py --run")
else:
    print("  ⛔ NOT READY — fix the ✗ items above. Main system stays on paper meanwhile.")
sys.exit(0 if allpass else 1)
