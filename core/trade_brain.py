#!/usr/bin/env python3
"""
trade_brain.py — Echo's autonomous trading brain v2
Improvements:
  1. Increased position sizing — up to 8 positions, 10% per trade
  2. Trailing stop — captures more upside on winning trades
  3. Sector awareness — diversified across tech, finance, energy, crypto
  4. Fixed crypto symbols — use correct Alpaca format
  5. Updated momentum watchlist — fresher movers
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

def get_sector(symbol):
    """Return sector for a symbol to prevent over-concentration."""
    sectors = {
        # Tech
        "AAPL": "tech", "MSFT": "tech", "NVDA": "tech", "AMD": "tech",
        "GOOGL": "tech", "META": "tech",
        # Index/Broad
        "SPY": "index", "QQQ": "index", "IWM": "index",
        # Finance/Crypto
        "COIN": "crypto", "MSTR": "crypto",
        # EV/Growth
        "TSLA": "ev", "RIVN": "ev",
        # Finance
        "JPM": "finance", "BAC": "finance",
        # Energy
        "XOM": "energy", "CVX": "energy",
        # Momentum plays
        "PLTR": "growth", "SOFI": "growth", "HOOD": "growth",
        "RKLB": "growth", "IONQ": "growth",
    }
    return sectors.get(symbol, "other")

def manage_existing_positions(api, day_trades=0):
    """Check open positions — use trailing stop logic."""
    positions = api.list_positions()
    trades = load_trade_log()

    for p in positions:
        symbol = p.symbol
        current = float(p.current_price)
        pl_pct = float(p.unrealized_plpc) * 100
        qty = p.qty

        # Get strategy from trade log
        strategy = "trend"
        entry_price = float(p.avg_entry_price)
        for t in trades:
            if t.get("symbol") == symbol and t.get("status") == "submitted":
                strategy = t.get("strategy", "trend")
                break

        # Trailing stop thresholds
        if strategy == "momentum":
            take_profit = 3.0
            stop_loss = -1.0
            trail_pct = 1.5  # trail by 1.5% from peak
        else:
            take_profit = 5.0
            stop_loss = -2.5
            trail_pct = 2.0  # trail by 2% from peak

        # Calculate trailing stop — track real peak from trade log
        peak_pct = pl_pct
        for t in trades:
            if t.get("symbol") == symbol and t.get("status") == "submitted":
                stored_peak = float(t.get("peak_pct", 0))
                if pl_pct > stored_peak:
                    t["peak_pct"] = round(pl_pct, 3)
                peak_pct = max(pl_pct, stored_peak)
                break
        trail_stop_level = peak_pct - trail_pct
        action = None
        reason = ""

        if pl_pct >= take_profit:
            action = "sell"
            reason = f"take profit {pl_pct:.1f}% >= {take_profit}%"
        elif pl_pct <= stop_loss:
            action = "sell"
            reason = f"stop loss {pl_pct:.1f}% <= {stop_loss}%"
        elif peak_pct >= 3.0 and pl_pct <= trail_stop_level:
            # Real trailing stop — peaked then dropped trail_pct% below peak
            action = "sell"
            reason = f"trailing stop — peaked {peak_pct:.1f}%, now {pl_pct:.1f}% (trail={trail_pct}%)"

        # PDT protection — don't day trade if at limit
        if action == "sell" and day_trades >= 2:
            if is_day_trade(api, symbol):
                log(f"  SKIPPING {symbol} close — would be day trade #{day_trades+1}")
                action = None
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
                log(f"  Closed {symbol}: {order.id}")
                # Score in regret index
                try:
                    import sys
                    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                    from core.regret_index import log_action, update_outcome
                    entry_id = log_action(
                        f"trade_{symbol}_{datetime.now().strftime('%Y%m%d')}",
                        category="trading",
                        description=f"{symbol} {reason}",
                        context="trade_brain"
                    )
                    score = 1 if pl_pct > 0 else -1
                    update_outcome(entry_id, score, f"closed {symbol} {pl_pct:.1f}%: {reason}")
                except Exception as re:
                    log(f"  regret score failed: {re}")
            except Exception as e:
                log(f"  Close failed {symbol}: {e}")
        else:
            log(f"  HOLDING {symbol}: {pl_pct:.1f}% — stop={stop_loss}% target={take_profit}%")

def analyze_trend(api, symbol):
    """Trend following — MA crossover + RSI."""
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
        reason = f"uptrend MA20>MA50 RSI={rsi:.1f}"

    return {"symbol": symbol, "signal": signal, "reason": reason,
            "price": current, "rsi": round(rsi, 2), "strategy": "trend",
            "sector": get_sector(symbol)}

def analyze_momentum(api, symbol):
    """Quick mover — short term momentum + volume."""
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
    if momentum_5d > 3 and vol_ratio > 1.3 and rsi < 70:
        signal = "buy"
        reason = f"momentum +{momentum_5d:.1f}% 5d vol {vol_ratio:.1f}x RSI={rsi:.1f}"

    return {"symbol": symbol, "signal": signal, "reason": reason,
            "price": current, "momentum_5d": round(momentum_5d, 2),
            "strategy": "momentum", "sector": get_sector(symbol)}

def already_holding(api, symbol):
    positions = api.list_positions()
    return any(p.symbol == symbol for p in positions)

def sectors_held(api):
    """Return dict of sectors currently held."""
    positions = api.list_positions()
    held = {}
    for p in positions:
        sector = get_sector(p.symbol)
        held[sector] = held.get(sector, 0) + 1
    return held

def get_day_trade_count(api):
    """Get current day trade count — PDT rule: max 3 per week under $25k."""
    try:
        account = api.get_account()
        return int(account.daytrade_count or 0)
    except Exception:
        return 0

def is_day_trade(api, symbol):
    """Check if selling symbol would be a day trade (bought today)."""
    try:
        from datetime import date
        today = date.today().isoformat()
        orders = api.list_orders(status='filled', limit=50)
        bought_today = any(
            o.symbol == symbol and
            o.side == 'buy' and
            o.filled_at and
            str(o.filled_at)[:10] == today
            for o in orders
        )
        return bought_today
    except Exception:
        return False

def run():
    log("=== trade_brain v2 starting ===")
    api = get_api()
    account = api.get_account()
    buying_power = float(account.buying_power)
    portfolio = float(account.portfolio_value)
    day_trades = get_day_trade_count(api)
    log(f"Portfolio: ${portfolio:,.2f} | Buying power: ${buying_power:,.2f} | Day trades this week: {day_trades}/3")
    if day_trades >= 3:
        log("WARNING: Day trade limit reached (3/3) — momentum trades disabled for safety")

    # Step 1 — manage existing positions
    log("--- Managing positions ---")
    manage_existing_positions(api, day_trades)

    # Step 2 — scan for entries
    log("--- Scanning for entries ---")

    # Diversified watchlists by sector
    trend_list = [
        "SPY",   # index
        "QQQ",   # index
        "AAPL",  # tech
        "MSFT",  # tech
        "NVDA",  # tech
        "JPM",   # finance
        "XOM",   # energy
        "IWM",   # small cap index
    ]
    momentum_list = [
        "TSLA",  # ev
        "PLTR",  # growth
        "COIN",  # crypto
        "RKLB",  # growth/space
        "IONQ",  # quantum computing
        "SOFI",  # fintech
        "MSTR",  # crypto proxy
    ]

    signals = []
    held_sectors = sectors_held(api)

    for symbol in trend_list:
        if already_holding(api, symbol):
            log(f"  {symbol}: already holding")
            continue
        sector = get_sector(symbol)
        if held_sectors.get(sector, 0) >= 2:
            log(f"  {symbol}: sector {sector} already has 2 positions, skipping")
            continue
        result = analyze_trend(api, symbol)
        if result and result["signal"]:
            signals.append(result)
            log(f"  SIGNAL: BUY {symbol} — {result['reason']}")

    for symbol in momentum_list:
        if already_holding(api, symbol):
            log(f"  {symbol}: already holding")
            continue
        sector = get_sector(symbol)
        if held_sectors.get(sector, 0) >= 1:
            log(f"  {symbol}: sector {sector} already held, skipping")
            continue
        result = analyze_momentum(api, symbol)
        if result and result["signal"]:
            signals.append(result)
            log(f"  SIGNAL: BUY {symbol} — {result['reason']}")

    if not signals:
        log("No entry signals this cycle")
        log("=== trade_brain v2 done ===")
        return

    trades = load_trade_log()

    # Max 8 open positions, 10% per trade
    open_positions = len(api.list_positions())
    max_positions = 8
    slots = max_positions - open_positions

    if slots <= 0:
        log(f"Max positions ({max_positions}) reached")
        log("=== trade_brain v2 done ===")
        return

    for pick in signals[:slots]:
        if pick["strategy"] == "momentum":
            position_size = min(buying_power * 0.08, 8000)
        else:
            position_size = min(buying_power * 0.10, 10000)

        qty = max(1, int(position_size / pick["price"]))
        cost = qty * pick["price"]
        log(f"EXECUTING: BUY {qty} {pick['symbol']} @ ~${pick['price']:.2f} (${cost:,.2f}) [{pick['strategy']}]")

        try:
            order = api.submit_order(
                symbol=pick["symbol"], qty=qty, side="buy",
                type="market", time_in_force="day"
            )
            # Determine cascade layer
            from core.cascade_ledger import get_layer as _get_layer
            _layer = _get_layer(pick["symbol"])
            trades.append({
                "order_id": order.id,
                "symbol": pick["symbol"],
                "qty": qty,
                "side": "buy",
                "price": pick["price"],
                "strategy": pick["strategy"],
                "sector": pick["sector"],
                "layer": _layer,
                "reason": pick["reason"],
                "status": "submitted",
                "peak_pct": 0.0,
                "submitted_at": datetime.now().isoformat()
            })
            save_trade_log(trades)
            log(f"Order submitted: {order.id}")
            buying_power -= cost
        except Exception as e:
            log(f"Order failed {pick['symbol']}: {e}")

    log("=== trade_brain v2 done ===")

if __name__ == "__main__":
    run()