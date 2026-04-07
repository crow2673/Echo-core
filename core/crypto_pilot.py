#!/usr/bin/env python3
"""
crypto_pilot.py — $100 real money pilot mode for Echo's crypto brain
All three AIs approved this design. Build before moving real money.

Controls:
- Pilot mode flag — separate from paper trading
- Max $20 per trade (not $50)
- Kill switch at -10% ($90 total equity)
- 4-6 hour frequency (not 2h)
- Slippage logging — expected vs actual fill
- ntfy alert if kill switch triggers
- BTC and ETH only
- 14 day pilot window
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parents[1]
PILOT_LOG = BASE / "memory/crypto_pilot_log.json"
LOG = BASE / "logs/crypto_pilot.log"
PILOT_CONFIG = BASE / "memory/crypto_pilot_config.json"

env_file = Path.home() / ".config/echo/golem.env"
for line in env_file.read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1)
        os.environ.setdefault(k, v)

# PILOT SETTINGS — approved by Claude + GPT + Grok
PILOT_CAPITAL = 100.0          # Total pilot capital
KILL_SWITCH_PCT = -10.0        # -10% = $90 triggers halt
MAX_TRADE_NOTIONAL = 20.0      # Max $20 per trade
MAX_POSITIONS = 2              # BTC + ETH only
PILOT_ASSETS = ["BTC/USD", "ETH/USD"]
PILOT_DAYS = 14                # 14 day window

logging.basicConfig(filename=LOG, level=logging.INFO, format='%(asctime)s %(message)s')

def log(msg):
    print(msg)
    logging.info(msg)

def load_pilot_config():
    """Load or initialize pilot config."""
    if PILOT_CONFIG.exists():
        return json.loads(PILOT_CONFIG.read_text())
    config = {
        "active": False,
        "start_date": None,
        "end_date": None,
        "starting_equity": PILOT_CAPITAL,
        "kill_switch_triggered": False,
        "kill_switch_equity": None,
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "live_api_key": None,
        "live_secret_key": None,
        "live_base_url": "https://api.alpaca.markets"
    }
    PILOT_CONFIG.write_text(json.dumps(config, indent=2))
    return config

def save_pilot_config(config):
    PILOT_CONFIG.write_text(json.dumps(config, indent=2))

def load_pilot_log():
    if PILOT_LOG.exists():
        return json.loads(PILOT_LOG.read_text())
    return []

def save_pilot_log(trades):
    PILOT_LOG.write_text(json.dumps(trades, indent=2, default=str))

def send_ntfy_alert(msg):
    """Send phone alert via ntfy."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://ntfy.sh/echo-alerts",
            data=msg.encode(),
            method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
        log(f"[pilot] ntfy sent: {msg[:50]}")
    except Exception as e:
        log(f"[pilot] ntfy failed: {e}")

def check_kill_switch(api, config):
    """Check if pilot equity has dropped below kill switch threshold."""
    try:
        account = api.get_account()
        equity = float(account.equity)
        starting = config["starting_equity"]
        pct_change = (equity - starting) / starting * 100
        
        if pct_change <= KILL_SWITCH_PCT:
            log(f"[pilot] KILL SWITCH TRIGGERED — equity ${equity:.2f} ({pct_change:.1f}%)")
            config["kill_switch_triggered"] = True
            config["kill_switch_equity"] = equity
            save_pilot_config(config)
            send_ntfy_alert(f"ECHO PILOT KILL SWITCH: equity ${equity:.2f} ({pct_change:.1f}%). All crypto trading halted.")
            return True
        
        log(f"[pilot] Equity check: ${equity:.2f} ({pct_change:+.1f}%) — safe")
        return False
    except Exception as e:
        log(f"[pilot] Kill switch check failed: {e}")
        return False

def check_pilot_window(config):
    """Check if pilot is within 14 day window."""
    if not config.get("start_date"):
        return False
    start = datetime.fromisoformat(config["start_date"])
    end = datetime.fromisoformat(config["end_date"])
    now = datetime.now()
    if now > end:
        log(f"[pilot] 14 day window expired on {config['end_date']}")
        return False
    days_left = (end - now).days
    log(f"[pilot] Day {(now - start).days + 1} of 14 — {days_left} days remaining")
    return True

def log_trade_with_slippage(symbol, side, expected_price, filled_price, qty, reason):
    """Log trade with slippage analysis — the key learning metric."""
    slippage = filled_price - expected_price
    slippage_pct = (slippage / expected_price) * 100
    trades = load_pilot_log()
    trade = {
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "expected_price": expected_price,
        "filled_price": filled_price,
        "slippage": round(slippage, 4),
        "slippage_pct": round(slippage_pct, 4),
        "reason": reason,
        "notional": round(filled_price * qty, 2)
    }
    trades.append(trade)
    save_pilot_log(trades)
    log(f"[pilot] Slippage: expected ${expected_price:.2f} got ${filled_price:.2f} ({slippage_pct:+.3f}%)")
    return trade

def activate_pilot(live_api_key, live_secret_key):
    """Activate the pilot — call this manually before funding."""
    config = load_pilot_config()
    config["active"] = True
    config["start_date"] = datetime.now().isoformat()
    config["end_date"] = (datetime.now() + timedelta(days=14)).isoformat()
    config["starting_equity"] = PILOT_CAPITAL
    config["kill_switch_triggered"] = False
    config["live_api_key"] = live_api_key
    config["live_secret_key"] = live_secret_key
    save_pilot_config(config)
    log(f"[pilot] ACTIVATED — 14 day window: {config['start_date']} to {config['end_date']}")
    send_ntfy_alert(f"Echo crypto pilot ACTIVATED. $100 real money. Kill switch at $90. 14 days.")
    return config

def get_pilot_api():
    """Get live API connection for pilot trading."""
    config = load_pilot_config()
    if not config.get("live_api_key"):
        raise ValueError("Pilot not activated — no live API keys configured")
    import alpaca_trade_api as tradeapi
    return tradeapi.REST(
        config["live_api_key"],
        config["live_secret_key"],
        config["live_base_url"]
    ), config

def run_pilot_check():
    """
    Run a full pilot status check.
    Call this to see current pilot state without trading.
    """
    config = load_pilot_config()
    print("\n=== CRYPTO PILOT STATUS ===")
    print(f"Active: {config.get('active', False)}")
    print(f"Kill switch triggered: {config.get('kill_switch_triggered', False)}")
    print(f"Start date: {config.get('start_date', 'not started')}")
    print(f"End date: {config.get('end_date', 'not started')}")
    print(f"Starting equity: ${config.get('starting_equity', 0):.2f}")
    
    trades = load_pilot_log()
    print(f"\nTotal trades logged: {len(trades)}")
    if trades:
        slippages = [t.get('slippage_pct', 0) for t in trades]
        avg_slippage = sum(slippages) / len(slippages)
        print(f"Average slippage: {avg_slippage:+.3f}%")
        print("\nRecent trades:")
        for t in trades[-5:]:
            print(f"  {t['timestamp'][:16]} {t['side'].upper()} {t['symbol']} @ ${t['filled_price']:.2f} slippage={t['slippage_pct']:+.3f}%")
    print("===========================\n")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        run_pilot_check()
    elif len(sys.argv) > 1 and sys.argv[1] == "activate":
        if len(sys.argv) < 4:
            print("Usage: python3 crypto_pilot.py activate <api_key> <secret_key>")
        else:
            activate_pilot(sys.argv[2], sys.argv[3])
    else:
        run_pilot_check()
