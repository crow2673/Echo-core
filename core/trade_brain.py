#!/usr/bin/env python3
"""
trade_brain.py — Echo's autonomous trading brain v2
Improvements:
  1. Increased position sizing — up to 8 positions, 1 per sector
  2. Market regime filter — SPY 200MA bull/bear
  3. Trailing stop tracks peak_pct
  4. Layer tagging for cascade ledger
  5. Regret index scoring on close
"""
import json
import logging
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
TRADE_LOG = BASE / "memory/trade_log.json"
LOG = BASE / "logs/trader.log"

logging.basicConfig(
    filename=str(LOG),
    level=logging.INFO,
    format="%(asctime)s %(message)s",
)

# ── Strategy universes ────────────────────────────────────────────────────────
# L3 is intentionally disabled: the old trend selector produced 0 wins in 18
# closed trades. Keep its historical symbols explicit for P&L reconciliation.
TREND_LIST = []
HISTORICAL_TREND_SYMBOLS = {
    "XOM", "CVX", "TLT", "XLF", "XLE", "XLK", "XLV", "XLU", "XLI", "XLP", "XLY",
}

# L4 remains active independently of L3's circuit breaker.
INDEX_LIST = ["SPY", "QQQ", "IWM", "DIA", "GLD"]
MOMENTUM_LIST = [
    "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL",
    "RKLB", "SOFI", "PLTR", "MSTR", "HOOD",
]

MAX_POSITIONS = 6
POSITION_SIZE_PCT = 0.08     # 8% per position
TREND_TAKE_PROFIT = 0.05
TREND_STOP_LOSS = 0.025
TREND_TRAIL_PCT = 0.015
MOMENTUM_TAKE_PROFIT = 0.04
MOMENTUM_STOP_LOSS = 0.02
MOMENTUM_TRAIL_PCT = 0.012

SECTOR_MAP = {
    "GLD": "commodities", "TLT": "bonds",
    "XLF": "financials", "XLE": "energy", "XLK": "tech",
    "XLV": "healthcare", "XLU": "utilities", "XLI": "industrials",
    "XLP": "staples", "XLY": "discretionary",
    "SPY": "index", "QQQ": "index", "IWM": "index", "DIA": "index",
    "NVDA": "tech", "TSLA": "auto", "AAPL": "tech", "MSFT": "tech",
    "AMZN": "retail", "META": "social", "GOOGL": "tech",
    "RKLB": "aerospace", "SOFI": "fintech", "PLTR": "defense",
    "MSTR": "crypto_proxy", "HOOD": "fintech",
}


def log(msg):
    print(msg, flush=True)
    logging.info(msg)


def load_env():
    env_file = Path.home() / ".config/echo/golem.env"
    env = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def get_api():
    env = load_env()
    key = env.get("ALPACA_API_KEY") or os.environ.get("ALPACA_API_KEY", "")
    secret = env.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY", "")
    base = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    return key, secret, base


def alpaca_get(path, key, secret, base):
    req = urllib.request.Request(
        f"{base}{path}",
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def alpaca_post(path, payload, key, secret, base):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def alpaca_delete(path, key, secret, base):
    req = urllib.request.Request(
        f"{base}{path}",
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
        method="DELETE",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_bars(symbol, key, secret, timeframe="1Day", limit=60):
    # request ~1.5x calendar days to account for weekends/holidays
    cal_days = int(limit * 1.5) + 30
    start = (datetime.now() - timedelta(days=cal_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = urllib.parse.urlencode({"timeframe": timeframe, "start": start, "limit": limit})
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars?{params}"
    req = urllib.request.Request(
        url,
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return [float(b["c"]) for b in data.get("bars", [])]
    except Exception as e:
        log(f"  bars error {symbol}: {e}")
        return []


def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [max(d, 0) for d in deltas[-period:]]
    losses = [abs(min(d, 0)) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def load_trade_log():
    if TRADE_LOG.exists():
        try:
            return json.loads(TRADE_LOG.read_text())
        except Exception:
            pass
    return {}


def save_trade_log(trades):
    TRADE_LOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = TRADE_LOG.with_suffix(".tmp")
    tmp.write_text(json.dumps(trades, indent=2, default=str))
    tmp.rename(TRADE_LOG)


def get_sector(symbol):
    return SECTOR_MAP.get(symbol, symbol.lower())


def get_held_sectors(positions):
    return {get_sector(p["symbol"]) for p in positions}


def get_day_trade_count(account):
    return int(account.get("daytrade_count", 0))


def is_day_trade(symbol, trades):
    today = date.today().isoformat()
    t = trades.get(symbol, {})
    entered = t.get("entered_at", "")
    return entered.startswith(today)


def get_market_regime(key, secret):
    """SPY above 200MA = bull, below = bear. Skip new longs in bear market."""
    prices = get_bars("SPY", key, secret, limit=210)
    if len(prices) < 200:
        log("  Regime check: insufficient SPY data — assuming bull")
        return "bull"
    ma200 = sum(prices[-200:]) / 200
    current = prices[-1]
    regime = "bull" if current > ma200 else "bear"
    log(f"  Market regime: SPY ${current:.2f} vs 200MA ${ma200:.2f} → {regime.upper()}")
    return regime


def audit_stop_orders(positions, key, secret, base, trades):
    """Ensure every open position has a stop. Place any missing."""
    try:
        open_orders = alpaca_get("/v2/orders?status=open", key, secret, base)
        stops_by_symbol = {o["symbol"] for o in open_orders if o.get("type") in ("stop", "stop_limit")}
        for p in positions:
            sym = p["symbol"]
            # Crypto symbols are managed by crypto_brain — skip them here
            if "/" in sym or sym.endswith("USD") and len(sym) <= 7:
                continue
            if sym not in stops_by_symbol:
                entry = float(trades.get(sym, {}).get("entry_price", p["avg_entry_price"]))
                strategy = trades.get(sym, {}).get("strategy", "trend")
                stop_pct = TREND_STOP_LOSS if strategy in ("trend", "index") else MOMENTUM_STOP_LOSS
                stop_price = round(entry * (1 - stop_pct), 2)
                qty = p["qty"]
                try:
                    alpaca_post("/v2/orders", {
                        "symbol": sym, "qty": qty, "side": "sell",
                        "type": "stop", "stop_price": str(stop_price),
                        "time_in_force": "gtc",
                    }, key, secret, base)
                    log(f"  [stop_audit] placed missing stop: {sym} @ ${stop_price}")
                except Exception as e:
                    log(f"  [stop_audit] failed for {sym}: {e}")
    except Exception as e:
        log(f"[stop_audit] error: {e}")


def manage_existing_positions(positions, key, secret, base, trades, day_trades, max_day_trades=3):
    """Check open positions — use trailing stop logic."""
    for p in positions:
        sym = p["symbol"]
        pl_pct = float(p["unrealized_plpc"])
        current_price = float(p["current_price"])
        strategy = trades.get(sym, {}).get("strategy", "trend")

        trend_style = strategy in ("trend", "index")
        take_profit = TREND_TAKE_PROFIT if trend_style else MOMENTUM_TAKE_PROFIT
        stop_loss = TREND_STOP_LOSS if trend_style else MOMENTUM_STOP_LOSS
        trail_pct = TREND_TRAIL_PCT if trend_style else MOMENTUM_TRAIL_PCT

        stored_peak = trades.get(sym, {}).get("peak_pct", pl_pct)
        if pl_pct > stored_peak:
            stored_peak = pl_pct
            trades.setdefault(sym, {})["peak_pct"] = stored_peak

        reason = None
        if pl_pct >= take_profit:
            reason = f"take profit {pl_pct:+.1%}"
        elif pl_pct <= -stop_loss:
            reason = f"trailing stop — peaked {stored_peak:+.1%} now {pl_pct:+.1%}"
        elif stored_peak >= 0.025 and pl_pct < (stored_peak - trail_pct):
            reason = f"trailing stop — peaked {stored_peak:+.1%} now {pl_pct:+.1%}"

        log(f"  {'SKIPPING' if not reason else 'CLOSING'} {sym}: {pl_pct:+.1%} — stop={-stop_loss:.1%} target={take_profit:.1%}")

        if reason:
            if is_day_trade(sym, trades) and day_trades >= max_day_trades:
                log(f"  close — would be day trade #{day_trades + 1}, skipping")
                continue
            try:
                alpaca_delete(f"/v2/positions/{sym}", key, secret, base)
                trades.setdefault(sym, {}).update({
                    "close_reason": reason,
                    "close_price": current_price,
                })
                if is_day_trade(sym, trades):
                    day_trades += 1
            except Exception as e:
                log(f"  Close failed {sym}: {e}")

    return day_trades


def analyze_trend(symbol, key, secret):
    """Trend following — MA crossover + RSI + slope + separation filters."""
    prices = get_bars(symbol, key, secret, limit=60)
    if len(prices) < 55:
        return None, "insufficient data"
    rsi = calc_rsi(prices)
    ma20 = sum(prices[-20:]) / 20
    ma50 = sum(prices[-50:]) / 50
    ma50_5ago = sum(prices[-55:-5]) / 50  # MA50 as of 5 trading days ago
    current = prices[-1]

    # MA50 must be rising (slope confirmation — not a decelerating trend)
    ma50_rising = ma50 > ma50_5ago
    # MA20 must be at least 0.5% above MA50 (real separation, not a false cross)
    separation_ok = (ma20 - ma50) / ma50 >= 0.005

    if not ma50_rising or not separation_ok:
        return None, f"no signal (MA50 slope={'up' if ma50_rising else 'flat/down'}, sep={((ma20-ma50)/ma50)*100:.2f}%)"

    # Condition 1: oversold bounce in confirmed uptrend
    if rsi < 40 and current > ma20:
        return "buy", f"RSI oversold {rsi:.0f} + above MA20 + rising MA50"
    # Condition 2: momentum entry — tightened from rsi<60 to rsi<50 (below neutral)
    if current > ma20 and rsi < 50:
        return "buy", f"uptrend MA20>MA50 RSI={rsi:.0f} (rising slope, sep={((ma20-ma50)/ma50)*100:.1f}%)"
    return None, f"no signal (RSI={rsi:.0f})"


def analyze_momentum(symbol, key, secret):
    """Quick mover — short term momentum + volume."""
    prices = get_bars(symbol, key, secret, limit=20)
    if len(prices) < 10:
        return None, "insufficient data"
    rsi = calc_rsi(prices, period=10)
    current = prices[-1]
    prev_5 = prices[-6] if len(prices) >= 6 else prices[0]
    momentum_5d = (current - prev_5) / prev_5
    ma10 = sum(prices[-10:]) / 10
    if rsi < 35 and current > ma10 and momentum_5d > 0:
        return "buy", f"RSI oversold {rsi:.0f} + above MA10 momentum={momentum_5d:+.1%}"
    return None, f"no signal (RSI={rsi:.0f}, mom={momentum_5d:+.1%})"


TREND_CIRCUIT_BREAKER_LOSSES = 3   # consecutive trend losses before pause
TREND_CIRCUIT_BREAKER_DAYS = 5    # trading days to wait after breaker trips


def check_trend_circuit_breaker(trades) -> tuple[bool, str]:
    """
    Returns (paused, reason). Trips after TREND_CIRCUIT_BREAKER_LOSSES
    consecutive closed trend losses and holds for TREND_CIRCUIT_BREAKER_DAYS.
    State is persisted in trades['_circuit_breaker'].
    """
    cb = trades.get("_circuit_breaker", {})
    pause_until = cb.get("pause_until")
    if pause_until:
        try:
            until_dt = datetime.fromisoformat(pause_until)
            if datetime.now() < until_dt:
                return True, f"circuit breaker active until {until_dt.strftime('%Y-%m-%d')} ({cb.get('consecutive_losses',0)} consecutive losses)"
        except Exception:
            pass

    # Count consecutive trend losses from most recent closed positions
    closed = [
        (sym, t) for sym, t in trades.items()
        if sym != "_circuit_breaker"
        and t.get("close_reason")
        and t.get("strategy", "trend") == "trend"
        and "take profit" not in t.get("close_reason", "")
    ]
    # Sort by close time if available
    closed.sort(key=lambda x: x[1].get("close_price", 0))
    consecutive = len(closed)  # all recent closes without a win resets the count

    # Check if most recent was a win — if so, reset
    wins = [
        (sym, t) for sym, t in trades.items()
        if sym != "_circuit_breaker"
        and "take profit" in t.get("close_reason", "")
        and t.get("strategy", "trend") == "trend"
    ]
    if wins:
        consecutive = 0  # a win resets the streak

    if consecutive >= TREND_CIRCUIT_BREAKER_LOSSES:
        pause_dt = datetime.now() + timedelta(days=TREND_CIRCUIT_BREAKER_DAYS)
        trades["_circuit_breaker"] = {
            "consecutive_losses": consecutive,
            "tripped_at": datetime.now().isoformat(),
            "pause_until": pause_dt.isoformat(),
        }
        reason = f"circuit breaker tripped — {consecutive} consecutive trend losses, pausing until {pause_dt.strftime('%Y-%m-%d')}"
        log(f"  [circuit_breaker] {reason}")
        try:
            from core.notifier import notify
            notify("L3 Circuit Breaker", f"{consecutive} consecutive trend losses — pausing new entries for {TREND_CIRCUIT_BREAKER_DAYS} days", urgent=True)
        except Exception:
            pass
        return True, reason

    return False, ""


def get_position_scalar(symbol, trades):
    """Scale down confidence based on recent regret scores."""
    try:
        from core.regret_index import get_flags
        flags = get_flags()
        flagged = {f[1] for f in flags}
        if symbol in flagged:
            return 0.5
    except Exception:
        pass
    return 1.0


def run():
    log("=== trade_brain v2 starting ===")
    key, secret, base = get_api()
    if not key:
        log("ERROR: no Alpaca credentials")
        return

    try:
        account = alpaca_get("/v2/account", key, secret, base)
        portfolio_value = float(account["portfolio_value"])
        buying_power = float(account["buying_power"])
        day_trades = get_day_trade_count(account)
        log(f"Portfolio: ${portfolio_value:,.2f} | Buying power: ${buying_power:,.2f} | Day trades this week: {day_trades}/3")
    except Exception as e:
        log(f"Account fetch failed: {e}")
        return

    if day_trades >= 3:
        log("WARNING: Day trade limit reached (3/3) — momentum trades disabled for safety")

    trades = load_trade_log()

    try:
        positions = alpaca_get("/v2/positions", key, secret, base)
    except Exception as e:
        log(f"Positions fetch failed: {e}")
        return

    log("--- Managing positions ---")
    audit_stop_orders(positions, key, secret, base, trades)
    day_trades = manage_existing_positions(positions, key, secret, base, trades, day_trades)

    # Re-fetch after any closes
    try:
        positions = alpaca_get("/v2/positions", key, secret, base)
    except Exception:
        pass

    if len(positions) >= MAX_POSITIONS:
        log(f"Max positions ({MAX_POSITIONS}) reached")
        save_trade_log(trades)
        log("=== trade_brain v2 done ===")
        return

    # Circuit breaker pauses L3 only. L4 index and L2 momentum remain independent.
    paused, pause_reason = check_trend_circuit_breaker(trades)
    if paused:
        log(f"TREND PAUSED: {pause_reason}")

    regime = get_market_regime(key, secret)
    if regime == "bear":
        log("BEAR MARKET: SPY below 200MA — skipping all new long entries this cycle")
        save_trade_log(trades)
        log("=== trade_brain v2 done ===")
        return

    held_sectors = get_held_sectors(positions)
    slots = MAX_POSITIONS - len(positions)
    signals = []

    log("--- Scanning for entries ---")
    if not paused:
        for symbol in TREND_LIST:
            if any(p["symbol"] == symbol for p in positions):
                log(f"  {symbol}: already holding")
                continue
            sector = get_sector(symbol)
            if sector in held_sectors:
                log(f"  {symbol}: sector already held, skipping")
                continue
            signal, reason = analyze_trend(symbol, key, secret)
            if signal:
                scalar = get_position_scalar(symbol, trades)
                if scalar < 0.6:
                    log(f"  {symbol}: low confidence in {signal} signal — beliefs gate")
                    continue
                signals.append((symbol, "trend", reason, scalar))
                log(f"  SIGNAL: BUY {symbol} ({reason})")

    for symbol in INDEX_LIST:
        if any(p["symbol"] == symbol for p in positions):
            log(f"  {symbol}: already holding")
            continue
        sector = get_sector(symbol)
        if sector in held_sectors:
            log(f"  {symbol}: sector already held, skipping")
            continue
        signal, reason = analyze_trend(symbol, key, secret)
        if signal:
            scalar = get_position_scalar(symbol, trades)
            if scalar < 0.6:
                log(f"  {symbol}: low confidence in {signal} signal — beliefs gate")
                continue
            signals.append((symbol, "index", reason, scalar))
            log(f"  SIGNAL: BUY {symbol} ({reason})")

    if day_trades < 3:
        for symbol in MOMENTUM_LIST:
            if any(p["symbol"] == symbol for p in positions):
                log(f"  {symbol}: already holding")
                continue
            sector = get_sector(symbol)
            if sector in held_sectors:
                continue
            signal, reason = analyze_momentum(symbol, key, secret)
            if signal:
                scalar = get_position_scalar(symbol, trades)
                if scalar < 0.6:
                    log(f"  {symbol}: low confidence in {signal} signal — beliefs gate")
                    continue
                signals.append((symbol, "momentum", reason, scalar))
                log(f"  SIGNAL: BUY {symbol} ({reason})")

    if not signals:
        log("No entry signals this cycle")
        save_trade_log(trades)
        log("=== trade_brain v2 done ===")
        return

    for symbol, strategy, reason, scalar in signals[:slots]:
        sector = get_sector(symbol)
        if sector in held_sectors:
            log(f"  {symbol} already held, skipping")
            continue

        stop_pct = TREND_STOP_LOSS if strategy in ("trend", "index") else MOMENTUM_STOP_LOSS
        position_usd = portfolio_value * POSITION_SIZE_PCT * scalar

        try:
            bars = get_bars(symbol, key, secret, limit=5)
            if not bars:
                continue
            current_price = bars[-1]
            qty = max(1, int(position_usd / current_price))
            stop_price = round(current_price * (1 - stop_pct), 2)

            log(f"EXECUTING: BUY {qty} {symbol} @ ~${current_price:.2f} (stop=${stop_price:.2f})")
            order = alpaca_post("/v2/orders", {
                "symbol": symbol,
                "qty": str(qty),
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            }, key, secret, base)
            log(f"Order submitted: {order.get('id', 'unknown')} status={order.get('status')}")

            # Place stop immediately
            try:
                stop_order = alpaca_post("/v2/orders", {
                    "symbol": symbol,
                    "qty": str(qty),
                    "side": "sell",
                    "type": "stop",
                    "stop_price": str(stop_price),
                    "time_in_force": "gtc",
                }, key, secret, base)
                log(f"Stop order placed: {symbol} @ ${stop_price}")
            except Exception as e:
                log(f"Stop order failed {symbol}: {e} — manual stop still active")

            trades[symbol] = {
                "strategy": strategy,
                "entry_price": current_price,
                "peak_pct": 0,
                "entered_at": datetime.now().isoformat(),
                "reason": reason,
            }
            held_sectors.add(sector)

        except Exception as e:
            log(f"Order failed {symbol}: {e}")

    save_trade_log(trades)
    log("=== trade_brain v2 done ===")


if __name__ == "__main__":
    run()
