#!/usr/bin/env python3
"""
trade_brain.py — Echo's autonomous trading brain
Strategies:
  1. Trend following — MA crossover + RSI on large caps (SPY, QQQ, AAPL etc)
  2. Quick movers — momentum plays on volatile stocks, tighter exits
Fully autonomous: opens positions, manages them, closes them.
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parents[1]
TRADE_LOG = BASE / "memory/trade_log.json"
LOG = BASE / "logs/trader.log"

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

def get_bars(api, symbol, limit=60):
    from datetime import datetime, timedelta
    end = datetime.now()
    start = end - timedelta(days=limit*2)
    try:
        bars = api.get_bars(symbol, '1Day', feed='iex',
            start=start.strftime('%Y-%m-%d'),
            end=end.strftime('%Y-%m-%d'),
            limit=limit).df
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

def manage_existing_positions(api):
    """Check open positions — close if take profit or stop loss hit."""
    positions = api.list_positions()
    trades = load_trade_log()

    for p in positions:
        symbol = p.symbol
        entry = float(p.avg_entry_price)
        current = float(p.current_price)
        pl_pct = float(p.unrealized_plpc) * 100
        qty = p.qty

        # Determine strategy type from trade log
        strategy = "trend"
        for t in trades:
            if t.get("symbol") == symbol and t.get("status") == "submitted":
                strategy = t.get("strategy", "trend")
                break

        # Exit thresholds
        if strategy == "momentum":
            take_profit = 2.0   # 2% gain
            stop_loss = -1.0    # 1% loss — tight
        else:
            take_profit = 4.0   # 4% gain
            stop_loss = -2.5    # 2.5% loss

        action = None
        reason = ""

        if pl_pct >= take_profit:
            action = "sell"
            reason = f"take profit hit {pl_pct:.1f}% >= {take_profit}%"
        elif pl_pct <= stop_loss:
            action = "sell"
            reason = f"stop loss hit {pl_pct:.1f}% <= {stop_loss}%"

        if action:
            log(f"  CLOSING {symbol}: {reason}")
            try:
                order = api.submit_order(
                    symbol=symbol, qty=qty, side="sell",
                    type="market", time_in_force="day"
                )
                for t in trades:
                    if t.get("symbol") == symbol and t.get("status") == "submitted":
                        t["status"] = "closed"
                        t["close_reason"] = reason
                        t["close_price"] = current
                        t["pl_pct"] = pl_pct
                        t["closed_at"] = datetime.now().isoformat()
                save_trade_log(trades)
                log(f"  Closed {symbol} order: {order.id}")
                # Score in regret index
                try:
                    import sys
                    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                    from core.regret_index import log_action, update_outcome
                    entry_id = log_action(f"trade_{symbol}_{datetime.now().strftime('%Y%m%d')}",
                        category="trading", description=f"{symbol} {reason}", context="trade_brain")
                    score = 1 if pl_pct > 0 else -1
                    update_outcome(entry_id, score, f"closed {symbol} {pl_pct:.1f}%: {reason}")
                except Exception as re:
                    log(f"  regret score failed: {re}")
            except Exception as e:
                log(f"  Close failed {symbol}: {e}")
        else:
            log(f"  HOLDING {symbol}: {pl_pct:.1f}% P/L — waiting for {take_profit}% or {stop_loss}%")

def analyze_trend(api, symbol):
    """Trend following strategy — MA crossover + RSI."""
    bars = get_bars(api, symbol)
    if bars is None or len(bars) < 20:
        return None
    close = bars['close']
    rsi = calc_rsi(close).iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(min(50, len(close))).mean().iloc[-1]
    current = close.iloc[-1]

    signal = None
    reason = ""
    if rsi < 35 and current > ma20:
        signal = "buy"
        reason = f"RSI oversold {rsi:.1f} + above MA20"
    elif current > ma20 > ma50 and rsi < 60:
        signal = "buy"
        reason = f"uptrend MA20>MA50, RSI={rsi:.1f}"

    return {"symbol": symbol, "signal": signal, "reason": reason,
            "price": current, "rsi": round(rsi, 2), "strategy": "trend"}

def analyze_momentum(api, symbol):
    """Quick mover strategy — short term momentum."""
    bars = get_bars(api, symbol, limit=20)
    if bars is None or len(bars) < 10:
        return None
    close = bars['close']
    rsi = calc_rsi(close).iloc[-1]
    current = close.iloc[-1]
    prev_5 = close.iloc[-6]
    momentum_5d = (current - prev_5) / prev_5 * 100
    volume = bars['volume']
    vol_ratio = volume.iloc[-1] / volume.iloc[-6:-1].mean() if volume.iloc[-6:-1].mean() > 0 else 1

    signal = None
    reason = ""
    # Strong momentum + volume confirmation + not overbought
    if momentum_5d > 3 and vol_ratio > 1.3 and rsi < 70:
        signal = "buy"
        reason = f"momentum +{momentum_5d:.1f}% 5d, vol {vol_ratio:.1f}x, RSI={rsi:.1f}"

    return {"symbol": symbol, "signal": signal, "reason": reason,
            "price": current, "momentum_5d": round(momentum_5d, 2),
            "vol_ratio": round(vol_ratio, 2), "strategy": "momentum"}

def already_holding(api, symbol):
    positions = api.list_positions()
    return any(p.symbol == symbol for p in positions)

def run():
    log("=== trade_brain starting ===")
    api = get_api()
    account = api.get_account()
    buying_power = float(account.buying_power)
    portfolio = float(account.portfolio_value)
    log(f"Portfolio: ${portfolio:,.2f} | Buying power: ${buying_power:,.2f}")

    # Step 1 — manage existing positions
    log("--- Managing positions ---")
    manage_existing_positions(api)

    # Step 2 — look for new entries
    log("--- Scanning for entries ---")

    # Trend watchlist — large cap, liquid
    trend_list = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMD"]
    # Momentum watchlist — volatile movers
    momentum_list = ["TSLA", "PLTR", "MSTR", "COIN", "SOFI", "HOOD"]

    signals = []
    for symbol in trend_list:
        if already_holding(api, symbol):
            log(f"  {symbol}: already holding, skip")
            continue
        log(f"  Analyzing {symbol} (trend)...")
        result = analyze_trend(api, symbol)
        if result and result["signal"]:
            signals.append(result)
            log(f"  SIGNAL: {result['signal'].upper()} {symbol} — {result['reason']}")

    for symbol in momentum_list:
        if already_holding(api, symbol):
            log(f"  {symbol}: already holding, skip")
            continue
        log(f"  Analyzing {symbol} (momentum)...")
        result = analyze_momentum(api, symbol)
        if result and result["signal"]:
            signals.append(result)
            log(f"  SIGNAL: {result['signal'].upper()} {symbol} — {result['reason']}")

    if not signals:
        log("No entry signals this cycle")
        log("=== trade_brain done ===")
        return

    trades = load_trade_log()

    # Max 3 open positions total
    open_positions = len(api.list_positions())
    max_positions = 3
    slots = max_positions - open_positions

    if slots <= 0:
        log(f"Max positions ({max_positions}) reached, no new entries")
        log("=== trade_brain done ===")
        return

    # Size positions
    for pick in signals[:slots]:
        if pick["strategy"] == "momentum":
            position_size = min(buying_power * 0.03, 2000)  # 3% max, $2k cap for quick movers
        else:
            position_size = min(buying_power * 0.05, 5000)  # 5% max, $5k cap for trend

        qty = max(1, int(position_size / pick["price"]))
        cost = qty * pick["price"]
        log(f"EXECUTING: BUY {qty} {pick['symbol']} @ ~${pick['price']:.2f} (${cost:,.2f}) [{pick['strategy']}]")

        try:
            order = api.submit_order(
                symbol=pick["symbol"], qty=qty, side="buy",
                type="market", time_in_force="day"
            )
            trades.append({
                "order_id": order.id,
                "symbol": pick["symbol"],
                "qty": qty,
                "side": "buy",
                "price": pick["price"],
                "strategy": pick["strategy"],
                "reason": pick["reason"],
                "status": "submitted",
                "submitted_at": datetime.now().isoformat()
            })
            save_trade_log(trades)
            log(f"Order submitted: {order.id}")
            buying_power -= cost
        except Exception as e:
            log(f"Order failed {pick['symbol']}: {e}")

    log("=== trade_brain done ===")

if __name__ == "__main__":
    run()
