#!/usr/bin/env python3
"""
trade_brain.py
Echo's trading brain — reads strategies, reasons about market conditions,
executes paper trades, scores outcomes through regret index.
"""
import os
import json
import requests
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parents[1]
STRATEGIES = BASE / "memory/trading_strategies.json"
TRADE_LOG = BASE / "memory/trade_log.json"
LOG = BASE / "logs/trader.log"

# Load keys
env_file = Path.home() / ".config/echo/golem.env"
for line in env_file.read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1)
        os.environ.setdefault(k, v)

API_KEY = os.environ.get("ALPACA_API_KEY")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

def log(msg):
    print(msg)
    with open(LOG, 'a') as f:
        f.write(f"{datetime.now()} {msg}\n")

def get_api():
    import alpaca_trade_api as tradeapi
    return tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL)

def get_bars(symbol, timeframe='1Day', limit=50):
    """Get recent price bars for a symbol"""
    api = get_api()
    end = datetime.now()
    start = end - timedelta(days=limit*2)
    bars = api.get_bars(symbol, timeframe, feed="iex",
        start=start.strftime('%Y-%m-%d'),
        end=end.strftime('%Y-%m-%d'),
        limit=limit).df
    return bars

def calc_rsi(prices, period=14):
    """Calculate RSI"""
    import pandas as pd
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calc_ma(prices, period):
    """Calculate moving average"""
    return prices.rolling(period).mean()

def analyze_symbol(symbol):
    """Analyze a symbol and return trade signal"""
    try:
        bars = get_bars(symbol)
        if bars.empty or len(bars) < 20:
            return None
        close = bars['close']
        rsi = calc_rsi(close).iloc[-1]
        ma20 = calc_ma(close, 20).iloc[-1]
        ma50 = calc_ma(close, min(50, len(close))).iloc[-1]
        current = close.iloc[-1]
        prev = close.iloc[-2]
        signal = None
        reason = ""
        if rsi < 35 and current > ma20:
            signal = "buy"
            reason = f"RSI oversold ({rsi:.1f}) + price above MA20"
        elif rsi > 65 and current < ma20:
            signal = "sell"
            reason = f"RSI overbought ({rsi:.1f}) + price below MA20"
        elif current > ma20 > ma50:
            signal = "buy"
            reason = f"Price above MA20 above MA50 (uptrend)"
        return {
            "symbol": symbol,
            "signal": signal,
            "reason": reason,
            "price": current,
            "rsi": round(rsi, 2),
            "ma20": round(ma20, 2),
            "analyzed_at": datetime.now().isoformat()
        }
    except Exception as e:
        log(f"Error analyzing {symbol}: {e}")
        return None

def load_trade_log():
    if TRADE_LOG.exists():
        return json.loads(TRADE_LOG.read_text())
    return []

def save_trade_log(trades):
    TRADE_LOG.write_text(json.dumps(trades, indent=2, default=str))

def run():
    log("=== trade_brain starting ===")
    api = get_api()
    account = api.get_account()
    buying_power = float(account.buying_power)
    log(f"Buying power: ${buying_power:,.2f}")

    # Watch list — diversified, liquid symbols
    watchlist = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMD", "BTCUSD", "ETHUSD"]
    signals = []
    for symbol in watchlist:
        log(f"Analyzing {symbol}...")
        result = analyze_symbol(symbol)
        if result and result["signal"]:
            signals.append(result)
            log(f"  SIGNAL: {result['signal'].upper()} {symbol} — {result['reason']}")

    if not signals:
        log("No signals found this cycle")
        return

    # Take the first buy signal, size at 5% of portfolio
    buy_signals = [s for s in signals if s["signal"] == "buy"]
    if buy_signals:
        pick = buy_signals[0]
        position_size = min(buying_power * 0.05, 5000)  # max $5k per trade
        qty = max(1, int(position_size / pick["price"]))
        log(f"EXECUTING: BUY {qty} {pick['symbol']} @ ~${pick['price']:.2f} (${qty * pick['price']:,.2f})")
        try:
            order = api.submit_order(
                symbol=pick["symbol"],
                qty=qty,
                side="buy",
                type="market",
                time_in_force="day"
            )
            trades = load_trade_log()
            trades.append({
                "order_id": order.id,
                "symbol": pick["symbol"],
                "qty": qty,
                "side": "buy",
                "price": pick["price"],
                "reason": pick["reason"],
                "status": "submitted",
                "submitted_at": datetime.now().isoformat()
            })
            save_trade_log(trades)
            log(f"Order submitted: {order.id}")
        except Exception as e:
            log(f"Order failed: {e}")
    log("=== trade_brain done ===")

if __name__ == "__main__":
    run()
