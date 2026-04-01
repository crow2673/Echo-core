#!/usr/bin/env python3
"""
crypto_brain.py — Echo's 24/7 crypto trading brain
Runs every 2 hours around the clock via systemd timer.
Uses Alpaca crypto API with correct BTC/USD ETH/USD format.
Strategies:
  - RSI mean reversion (crypto is more volatile, tighter bands)
  - Momentum (crypto moves faster than stocks)
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parents[1]
TRADE_LOG = BASE / "memory/crypto_trade_log.json"
LOG = BASE / "logs/crypto_trader.log"

env_file = Path.home() / ".config/echo/golem.env"
for line in env_file.read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1)
        os.environ.setdefault(k, v)

API_KEY = os.environ.get("ALPACA_API_KEY")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

logging.basicConfig(filename=LOG, level=logging.INFO, format='%(asctime)s %(message)s')

def log(msg):
    print(msg)
    logging.info(msg)

def get_api():
    import alpaca_trade_api as tradeapi
    return tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL)

def get_crypto_bars(api, symbol, limit=30):
    """Get crypto bars using correct Alpaca crypto endpoint."""
    end = datetime.now()
    start = end - timedelta(days=limit*2)
    try:
        bars = api.get_crypto_bars(
            symbol, '1Hour',
            start=start.strftime('%Y-%m-%dT%H:%M:%SZ'),
            end=end.strftime('%Y-%m-%dT%H:%M:%SZ'),
            limit=limit
        ).df
        return bars if not bars.empty else None
    except Exception as e:
        log(f"  bars error {symbol}: {e}")
        return None

def calc_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def load_trade_log():
    if TRADE_LOG.exists():
        return json.loads(TRADE_LOG.read_text())
    return []

def save_trade_log(trades):
    TRADE_LOG.write_text(json.dumps(trades, indent=2, default=str))

def already_holding_crypto(api, symbol):
    """Check if holding a crypto position."""
    try:
        positions = api.list_positions()
        clean = symbol.replace("/", "")
        return any(p.symbol == clean or p.symbol == symbol for p in positions)
    except Exception:
        return False

def manage_crypto_positions(api):
    """Manage open crypto positions with tighter stops."""
    try:
        positions = api.list_positions()
        trades = load_trade_log()
        crypto_symbols = {"BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD"}

        for p in positions:
            if p.symbol not in crypto_symbols:
                continue
            pl_pct = float(p.unrealized_plpc) * 100
            current = float(p.current_price)
            qty = p.qty

            # Crypto: tighter take profit, tighter stop
            take_profit = 4.0
            stop_loss = -2.0

            action = None
            reason = ""
            if pl_pct >= take_profit:
                action = "sell"
                reason = f"take profit {pl_pct:.1f}% >= {take_profit}%"
            elif pl_pct <= stop_loss:
                action = "sell"
                reason = f"stop loss {pl_pct:.1f}% <= {stop_loss}%"

            if action:
                log(f"  CLOSING {p.symbol}: {reason}")
                try:
                    order = api.submit_order(
                        symbol=p.symbol, qty=qty, side="sell",
                        type="market", time_in_force="gtc"
                    )
                    for t in trades:
                        if t.get("symbol") == p.symbol and t.get("status") == "submitted":
                            t["status"] = "closed"
                            t["close_reason"] = reason
                            t["close_price"] = current
                            t["pl_pct"] = pl_pct
                            t["closed_at"] = datetime.now().isoformat()
                    save_trade_log(trades)
                    log(f"  Closed {p.symbol}: {order.id}")
                except Exception as e:
                    log(f"  Close failed {p.symbol}: {e}")
            else:
                log(f"  HOLDING {p.symbol}: {pl_pct:.1f}%")
    except Exception as e:
        log(f"manage_crypto_positions error: {e}")

def analyze_crypto(api, symbol):
    """Analyze crypto using hourly bars — RSI + momentum."""
    bars = get_crypto_bars(api, symbol)
    if bars is None or len(bars) < 15:
        return None

    close = bars['close']
    rsi = calc_rsi(close).iloc[-1]
    current = close.iloc[-1]
    ma10 = close.rolling(10).mean().iloc[-1]
    prev_6h = close.iloc[-7] if len(close) > 6 else close.iloc[0]
    momentum_6h = (current - prev_6h) / prev_6h * 100

    signal = None
    reason = ""

    # RSI oversold + above short MA = buy signal
    if rsi < 35 and current > ma10:
        signal = "buy"
        reason = f"RSI oversold {rsi:.1f} + above MA10"
    # Strong momentum + not overbought
    elif momentum_6h > 2.5 and rsi < 65:
        signal = "buy"
        reason = f"momentum +{momentum_6h:.1f}% 6h RSI={rsi:.1f}"

    return {
        "symbol": symbol,
        "signal": signal,
        "reason": reason,
        "price": current,
        "rsi": round(rsi, 2),
        "momentum_6h": round(momentum_6h, 2)
    }

def run():
    log("=== crypto_brain starting ===")
    api = get_api()
    account = api.get_account()
    buying_power = float(account.buying_power)
    portfolio = float(account.portfolio_value)
    log(f"Portfolio: ${portfolio:,.2f} | Buying power: ${buying_power:,.2f}")

    # Manage existing crypto positions
    log("--- Managing crypto positions ---")
    manage_crypto_positions(api)

    # Scan for entries
    log("--- Scanning crypto ---")
    crypto_watchlist = ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD"]
    signals = []

    for symbol in crypto_watchlist:
        clean = symbol.replace("/", "")
        if already_holding_crypto(api, symbol):
            log(f"  {symbol}: already holding")
            continue
        result = analyze_crypto(api, symbol)
        if result and result["signal"]:
            signals.append(result)
            log(f"  SIGNAL: BUY {symbol} — {result['reason']}")
        else:
            rsi_str = f"RSI={result['rsi']}" if result else "no data"
            log(f"  {symbol}: no signal ({rsi_str})")

    if not signals:
        log("No crypto signals this cycle")
        log("=== crypto_brain done ===")
        return

    trades = load_trade_log()

    # Max 2 crypto positions, 5% each
    crypto_positions = sum(1 for t in trades
                          if t.get("status") == "submitted"
                          and t.get("symbol", "").endswith("USD")
                          and t.get("symbol") not in {"BTCUSD", "ETHUSD"} or
                          t.get("symbol") in {"BTCUSD", "ETHUSD"})
    slots = max(0, 2 - crypto_positions)

    if slots <= 0:
        log("Max crypto positions reached")
        log("=== crypto_brain done ===")
        return

    for pick in signals[:slots]:
        position_size = min(buying_power * 0.05, 5000)
        qty = position_size / pick["price"]
        qty = round(qty, 4)

        if qty <= 0:
            continue

        log(f"EXECUTING: BUY {qty} {pick['symbol']} @ ~${pick['price']:,.2f} (${qty * pick['price']:,.2f})")
        try:
            order = api.submit_order(
                symbol=pick["symbol"],
                qty=str(qty),
                side="buy",
                type="market",
                time_in_force="gtc"  # crypto uses gtc not day
            )
            trades.append({
                "order_id": order.id,
                "symbol": pick["symbol"].replace("/", ""),
                "qty": qty,
                "side": "buy",
                "price": pick["price"],
                "strategy": "crypto",
                "reason": pick["reason"],
                "status": "submitted",
                "submitted_at": datetime.now().isoformat()
            })
            save_trade_log(trades)
            log(f"Order submitted: {order.id}")
        except Exception as e:
            log(f"Order failed {pick['symbol']}: {e}")

    log("=== crypto_brain done ===")

if __name__ == "__main__":
    run()
