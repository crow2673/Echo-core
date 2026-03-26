#!/usr/bin/env python3
"""
trader.py
Echo's paper trading engine — Alpaca integration.
Connects to Alpaca paper trading, manages positions, executes trades.
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/trader.log"
MEMORY = BASE / "memory/trader_state.json"

# Load keys from env file
env_file = Path.home() / ".config/echo/golem.env"
for line in env_file.read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1)
        os.environ.setdefault(k, v)

API_KEY = os.environ.get("ALPACA_API_KEY")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2")

logging.basicConfig(filename=LOG, level=logging.INFO,
    format='%(asctime)s %(message)s')

def log(msg):
    print(msg)
    logging.info(msg)

def get_account():
    import alpaca_trade_api as tradeapi
    api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL)
    account = api.get_account()
    return account

def get_positions():
    import alpaca_trade_api as tradeapi
    api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL)
    return api.list_positions()

def place_order(symbol, qty, side, order_type='market'):
    import alpaca_trade_api as tradeapi
    api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL)
    order = api.submit_order(
        symbol=symbol,
        qty=qty,
        side=side,
        type=order_type,
        time_in_force='day'
    )
    log(f"ORDER: {side} {qty} {symbol} — id:{order.id}")
    return order

def save_state(data):
    MEMORY.write_text(json.dumps(data, indent=2, default=str))

if __name__ == "__main__":
    log("=== trader.py starting ===")
    account = get_account()
    log(f"Account: {account.id}")
    log(f"Cash buying power: ${float(account.buying_power):,.2f}")
    log(f"Portfolio value: ${float(account.portfolio_value):,.2f}")
    log(f"Status: {account.status}")
    positions = get_positions()
    log(f"Open positions: {len(positions)}")
    save_state({
        "last_check": datetime.now().isoformat(),
        "buying_power": float(account.buying_power),
        "portfolio_value": float(account.portfolio_value),
        "status": account.status,
        "positions": len(positions)
    })
    log("=== trader.py done ===")
