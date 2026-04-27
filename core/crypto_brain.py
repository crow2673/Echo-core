#!/usr/bin/env python3
"""
crypto_brain.py — Echo's 24/7 crypto trading brain
Runs every 2 hours around the clock via systemd timer.
Uses Alpaca crypto API with correct v1beta3 endpoint.
Strategy: RSI oversold + MA10 confluence on 1h bars.
"""
import json
import logging
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
TRADE_LOG = BASE / "memory/crypto_trade_log.json"
LOG = BASE / "logs/crypto_trader.log"

logging.basicConfig(
    filename=str(LOG),
    level=logging.INFO,
    format="%(asctime)s %(message)s",
)

CRYPTO_WATCHLIST = ["BTC/USD", "ETH/USD", "SOL/USD"]
MAX_CRYPTO_POSITIONS = 2
POSITION_SIZE_PCT = 0.05     # 5% of portfolio per position
TAKE_PROFIT_PCT = 0.06       # 6% take profit
STOP_LOSS_PCT = 0.03         # 3% stop loss
TRAIL_PCT = 0.02             # 2% trailing stop from peak


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


def get_crypto_bars(symbol, key, secret, limit=48):
    """Fetch hourly bars from Alpaca crypto endpoint."""
    start = (datetime.now() - timedelta(hours=limit + 5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    encoded_sym = urllib.parse.quote(symbol, safe="")  # BTC/USD -> BTC%2FUSD
    params = urllib.parse.urlencode({"timeframe": "1Hour", "limit": limit, "start": start})
    url = f"https://data.alpaca.markets/v1beta3/crypto/us/bars?symbols={encoded_sym}&{params}"
    req = urllib.request.Request(
        url,
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        bars = data.get("bars", {}).get(symbol, [])  # key is "BTC/USD" in response
        return [float(b["c"]) for b in bars]
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
    TRADE_LOG.write_text(json.dumps(trades, indent=2, default=str))


def already_holding_crypto(symbol, positions):
    clean = symbol.replace("/", "")
    return any(p["symbol"] == clean for p in positions)


def manage_crypto_positions(positions, key, secret, base, trades):
    """Manage open positions: take profit, stop loss, trailing stop."""
    for p in positions:
        sym = p["symbol"]
        pl_pct = float(p["unrealized_plpc"])
        current_price = float(p["current_price"])
        avg_entry = float(p["avg_entry_price"])

        stored = trades.get(sym, {})
        peak_pct = stored.get("peak_pct", pl_pct)
        if pl_pct > peak_pct:
            peak_pct = pl_pct
            trades.setdefault(sym, {})["peak_pct"] = peak_pct

        reason = None
        if pl_pct >= TAKE_PROFIT_PCT:
            reason = f"take profit {pl_pct:.1%}"
        elif pl_pct <= -STOP_LOSS_PCT:
            reason = f"stop loss {pl_pct:.1%}"
        elif peak_pct >= 0.03 and pl_pct < (peak_pct - TRAIL_PCT):
            reason = f"trailing stop — peaked {peak_pct:.1%} now {pl_pct:.1%}"

        if reason:
            try:
                encoded = urllib.parse.quote(sym, safe="")
                result = alpaca_delete(f"/v2/positions/{encoded}", key, secret, base)
                log(f"  CLOSING {sym}: {reason} @ ${current_price:.2f}")
                trades.setdefault(sym, {}).update({
                    "close_reason": reason,
                    "close_price": current_price,
                    "closed_at": datetime.now().isoformat(),
                    "peak_pct": 0,
                })
            except Exception as e:
                log(f"  Close failed {sym}: {e}")
        else:
            log(f"  HOLDING {sym}: {pl_pct:+.1%} (peak {peak_pct:+.1%})")


def analyze_crypto(symbol, key, secret):
    """RSI + MA10 momentum signal on 1h bars."""
    prices = get_crypto_bars(symbol, key, secret, limit=48)
    if len(prices) < 15:
        return None, f"insufficient data ({len(prices)} bars)"

    rsi = calc_rsi(prices, period=14)
    ma10 = sum(prices[-10:]) / 10
    current = prices[-1]
    prev_6h = prices[-7] if len(prices) >= 7 else prices[0]
    momentum_6h = (current - prev_6h) / prev_6h

    rsi_str = f"RSI={rsi:.0f}"

    if rsi < 35 and current > ma10:
        return "buy", f"RSI oversold {rsi_str} + above MA10 (confluence)"

    return None, f"no signal ({rsi_str}, momentum_6h={momentum_6h:+.1%})"


def run():
    log("=== crypto_brain starting ===")
    key, secret, base = get_api()
    if not key:
        log("ERROR: no Alpaca credentials")
        return

    try:
        account = alpaca_get("/v2/account", key, secret, base)
        portfolio_value = float(account["portfolio_value"])
        buying_power = float(account["buying_power"])
        log(f"Portfolio: ${portfolio_value:,.2f} | Buying power: ${buying_power:,.2f}")
    except Exception as e:
        log(f"Account fetch failed: {e}")
        return

    trades = load_trade_log()

    try:
        all_positions = alpaca_get("/v2/positions", key, secret, base)
        crypto_positions = [p for p in all_positions if "/" in p["symbol"] or
                           any(c in p["symbol"] for c in ["BTC", "ETH", "SOL"])]
    except Exception as e:
        log(f"Positions fetch failed: {e}")
        return

    log("--- Managing crypto positions ---")
    if crypto_positions:
        manage_crypto_positions(crypto_positions, key, secret, base, trades)
    else:
        log("  No open crypto positions")

    # Re-fetch after any closes
    try:
        all_positions = alpaca_get("/v2/positions", key, secret, base)
        crypto_positions = [p for p in all_positions if "/" in p["symbol"] or
                           any(c in p["symbol"] for c in ["BTC", "ETH", "SOL"])]
    except Exception:
        pass

    if len(crypto_positions) >= MAX_CRYPTO_POSITIONS:
        log(f"Max crypto positions reached ({MAX_CRYPTO_POSITIONS})")
        save_trade_log(trades)
        log("=== crypto_brain done ===")
        return

    log("--- Scanning crypto ---")
    slots = MAX_CRYPTO_POSITIONS - len(crypto_positions)
    signals = []

    for symbol in CRYPTO_WATCHLIST:
        if already_holding_crypto(symbol, crypto_positions):
            log(f"  {symbol}: already holding")
            continue
        signal, reason = analyze_crypto(symbol, key, secret)
        if signal == "buy":
            signals.append((symbol, reason))
            log(f"  SIGNAL: BUY {symbol} — {reason}")
        else:
            log(f"  {symbol}: no signal ({reason})")

    if not signals:
        log("No crypto signals this cycle")
        save_trade_log(trades)
        log("=== crypto_brain done ===")
        return

    for symbol, reason in signals[:slots]:
        try:
            # Get current price for sizing
            bars = get_crypto_bars(symbol, key, secret, limit=2)
            if not bars:
                continue
            current_price = bars[-1]
            position_usd = portfolio_value * POSITION_SIZE_PCT
            qty = round(position_usd / current_price, 6)
            if qty <= 0:
                continue

            log(f"EXECUTING: BUY {qty} {symbol} @ ~${current_price:,.2f}")
            result = alpaca_post("/v2/orders", {
                "symbol": symbol,
                "qty": str(qty),
                "side": "buy",
                "type": "market",
                "time_in_force": "gtc",
            }, key, secret, base)
            log(f"Order submitted: {result.get('id', 'unknown')} status={result.get('status')}")
            trades.setdefault(clean, {}).update({
                "entry_price": current_price,
                "peak_pct": 0,
                "reason": reason,
                "entered_at": datetime.now().isoformat(),
            })
        except Exception as e:
            log(f"Order failed {symbol}: {e}")

    save_trade_log(trades)
    log("=== crypto_brain done ===")


if __name__ == "__main__":
    run()
