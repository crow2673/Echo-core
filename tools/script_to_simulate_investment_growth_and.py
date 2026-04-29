#!/usr/bin/env python3
"""
Simulate investment growth and risk for Echo's tracked capital.
Writes a snapshot to memory/investment_snapshot.md for Telegram context.
"""

import logging
import random
import sys
import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG_FILE = BASE / 'logs' / 'investment_simulation.log'
MEMORY_DIR = BASE / 'memory'

logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s %(message)s')

sys.path.insert(0, str(BASE))
from core.notifier import notify

env_file = Path.home() / ".config/echo/golem.env"
ENV = {}
try:
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                ENV[k] = v
except Exception:
    pass


def simulate_investment(principal, annual_growth_pct, annual_risk_pct, years, runs=500):
    """
    Monte Carlo simulation — run `runs` times and return (median, p10, p90).
    Gives a range rather than a single misleading number.
    """
    results = []
    for _ in range(runs):
        value = principal
        for _ in range(years):
            noise = random.uniform(-annual_risk_pct, annual_risk_pct) / 100
            value *= 1 + (annual_growth_pct / 100) + noise
        results.append(value)
    results.sort()
    n = len(results)
    return results[n // 2], results[n // 10], results[n * 9 // 10]


def main():
    # Pull capital from Alpaca paper account if available, else fall back to ENV/defaults
    principal = float(ENV.get('INITIAL_INVESTMENT', 10000))
    try:
        trade_log = BASE / 'memory' / 'crypto_trade_log.json'
        if trade_log.exists():
            pass  # placeholder — could read portfolio value from trade log in future
    except Exception:
        pass

    growth_rate = float(ENV.get('GROWTH_RATE', 7))     # % per year
    risk_factor = float(ENV.get('RISK_FACTOR', 15))    # % annual volatility (crypto-realistic)
    years = int(ENV.get('YEARS', 5))

    try:
        median, p10, p90 = simulate_investment(principal, growth_rate, risk_factor, years)
        snapshot_path = MEMORY_DIR / 'investment_snapshot.md'
        tmp = snapshot_path.with_suffix('.tmp')
        tmp.write_text(
            f"# Investment Simulation Snapshot\n"
            f"- Principal: ${principal:,.2f}\n"
            f"- Horizon: {years} years @ {growth_rate}% growth, ±{risk_factor}% annual volatility\n"
            f"- Median outcome: ${median:,.2f}\n"
            f"- Conservative (10th pct): ${p10:,.2f}\n"
            f"- Optimistic (90th pct): ${p90:,.2f}\n"
            f"- Last run: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        )
        tmp.rename(snapshot_path)
        logging.info(f"Simulation done — median ${median:,.0f} range ${p10:,.0f}–${p90:,.0f}")
    except Exception as e:
        notify("Simulation Error", str(e), urgent=True)
        logging.error(f"Simulation error: {e}")


if __name__ == "__main__":
    main()
