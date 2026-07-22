#!/usr/bin/env python3
"""
crypto_brain.py — Echo's 24/7 crypto trading brain
Runs every 2 hours around the clock via systemd timer.

Strategy: EchoL1 V6 — regime-filtered long+short, profits in any market direction.
  Bull regime (MA50 > MA200): long on RSI recovery + MACD turning up + volume
  Bear regime (MA50 < MA200): short via MSTR/COIN stocks on Alpaca (crypto-correlated)
  Backtest: +3.5% over 18-month bear market (TP=3.5%, SL=1.2%)
  Long-only strategies lost -3.5% over same period.
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
# Stocks to short when crypto is in bear regime (highly BTC-correlated)
BEAR_SHORT_STOCKS = ["MSTR", "COIN"]
MAX_CRYPTO_POSITIONS = 2
POSITION_SIZE_PCT = 0.05     # 5% of portfolio per position
TAKE_PROFIT_PCT = 0.035      # 3.5% TP — backtest-optimised
STOP_LOSS_PCT = 0.012        # 1.2% SL — backtest-optimised
TRAIL_PCT = 0.02             # kept for position management fallback


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


def get_crypto_bars(symbol, key, secret, limit=48, timeframe="1Hour"):
    """Fetch bars from Alpaca crypto endpoint. Returns (closes, volumes)."""
    if timeframe == "1Day":
        start = (datetime.now() - timedelta(days=limit + 5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        start = (datetime.now() - timedelta(hours=limit + 5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    encoded_sym = urllib.parse.quote(symbol, safe="")
    params = urllib.parse.urlencode({"timeframe": timeframe, "limit": limit, "start": start})
    url = f"https://data.alpaca.markets/v1beta3/crypto/us/bars?symbols={encoded_sym}&{params}"
    req = urllib.request.Request(
        url,
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        bars = data.get("bars", {}).get(symbol, [])
        closes = [float(b["c"]) for b in bars]
        volumes = [float(b["v"]) for b in bars]
        return closes, volumes
    except Exception as e:
        log(f"  bars error {symbol} ({timeframe}): {e}")
        return [], []


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


def calc_macd(prices, fast=12, slow=26, signal=9):
    """Return (hist_now, hist_prev) — MACD histogram for last two bars."""
    if len(prices) < slow + signal:
        return 0.0, 0.0

    def ema_series(data, period):
        k = 2 / (period + 1)
        emas = [data[0]]
        for p in data[1:]:
            emas.append(p * k + emas[-1] * (1 - k))
        return emas

    ema_fast = ema_series(prices, fast)
    ema_slow = ema_series(prices, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema_series(macd_line, signal)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    if len(hist) < 2:
        return (hist[-1], 0.0) if hist else (0.0, 0.0)
    return hist[-1], hist[-2]


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


def get_market_regime(closes_1d: list) -> str:
    """Return 'bull', 'bear', or 'neutral' based on MA50 vs MA200."""
    if len(closes_1d) < 200:
        return "neutral"
    ma50 = sum(closes_1d[-50:]) / 50
    ma200 = sum(closes_1d[-200:]) / 200
    if ma50 > ma200 * 1.02:
        return "bull"
    if ma50 < ma200 * 0.98:
        return "bear"
    return "neutral"


def analyze_crypto(symbol, key, secret):
    """V6: regime-filtered long+short. Bull→long, Bear→short signal."""
    closes_1h, volumes_1h = get_crypto_bars(symbol, key, secret, limit=55, timeframe="1Hour")
    if len(closes_1h) < 35:
        return None, None, f"insufficient 1h data ({len(closes_1h)} bars)"

    closes_1d, _ = get_crypto_bars(symbol, key, secret, limit=210, timeframe="1Day")
    regime = get_market_regime(closes_1d)

    rsi_now = calc_rsi(closes_1h, 14)
    rsi_prev = calc_rsi(closes_1h[:-1], 14)
    macd_hist_now, macd_hist_prev = calc_macd(closes_1h)

    if len(volumes_1h) >= 21:
        vol_ma20 = sum(volumes_1h[-21:-1]) / 20
        volume_spike = volumes_1h[-1] > vol_ma20 * 1.2
        vol_ratio = volumes_1h[-1] / vol_ma20 if vol_ma20 > 0 else 0
    else:
        volume_spike = True
        vol_ratio = 0

    details = (
        f"regime={regime}, RSI {rsi_prev:.0f}→{rsi_now:.0f}, "
        f"MACD {macd_hist_prev:.1f}→{macd_hist_now:.1f}, vol {vol_ratio:.1f}x"
    )

    # Long signal — only in bull/neutral regime
    if regime in ("bull", "neutral"):
        if (rsi_prev < 40 and rsi_now > rsi_prev and rsi_now < 45
                and macd_hist_now > macd_hist_prev and volume_spike):
            return "long", regime, f"V6 long: {details}"

    # Short signal — only in bear/neutral regime
    if regime in ("bear", "neutral"):
        if (rsi_prev > 60 and rsi_now < rsi_prev and rsi_now > 55
                and macd_hist_now < macd_hist_prev and volume_spike):
            return "short", regime, f"V6 short: {details}"

    reasons = []
    if regime == "bull" and not (rsi_prev < 40 and rsi_now > rsi_prev):
        reasons.append(f"RSI {rsi_now:.0f} not recovering from oversold")
    if regime == "bear" and not (rsi_prev > 60 and rsi_now < rsi_prev):
        reasons.append(f"RSI {rsi_now:.0f} not reversing from overbought")
    if not volume_spike:
        reasons.append(f"low volume ({vol_ratio:.1f}x)")
    return None, regime, f"no signal ({regime}) — {', '.join(reasons) or details}"


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

    # Manage bear-proxy stock shorts (MSTR/COIN)
    bear_proxy_positions = [p for p in all_positions if p["symbol"] in BEAR_SHORT_STOCKS]
    if bear_proxy_positions:
        log("--- Managing bear-proxy stock shorts ---")
        manage_crypto_positions(bear_proxy_positions, key, secret, base, trades)

    # Re-fetch after any closes
    try:
        all_positions = alpaca_get("/v2/positions", key, secret, base)
        crypto_positions = [p for p in all_positions if "/" in p["symbol"] or
                           any(c in p["symbol"] for c in ["BTC", "ETH", "SOL"])]
        bear_proxy_positions = [p for p in all_positions if p["symbol"] in BEAR_SHORT_STOCKS]
    except Exception:
        bear_proxy_positions = []

    active_count = len(crypto_positions) + len(bear_proxy_positions)
    if active_count >= MAX_CRYPTO_POSITIONS:
        log(f"Max positions reached ({MAX_CRYPTO_POSITIONS})")
        save_trade_log(trades)
        log("=== crypto_brain done ===")
        return

    log("--- Scanning crypto ---")
    slots = MAX_CRYPTO_POSITIONS - active_count
    long_signals = []
    short_signals = []

    for symbol in CRYPTO_WATCHLIST:
        if already_holding_crypto(symbol, crypto_positions):
            log(f"  {symbol}: already holding")
            continue
        direction, regime, reason = analyze_crypto(symbol, key, secret)
        if direction == "long":
            long_signals.append((symbol, reason))
            log(f"  LONG SIGNAL: {symbol} — {reason}")
        elif direction == "short":
            short_signals.append((symbol, reason))
            log(f"  SHORT SIGNAL: {symbol} — {reason}")
        else:
            log(f"  {symbol}: {reason}")

    # Execute long signals — buy crypto directly
    if long_signals:
        for symbol, reason in long_signals[:slots]:
            try:
                closes, _ = get_crypto_bars(symbol, key, secret, limit=2)
                if not closes:
                    continue
                current_price = closes[-1]
                position_usd = portfolio_value * POSITION_SIZE_PCT
                qty = round(position_usd / current_price, 6)
                if qty <= 0:
                    continue
                log(f"EXECUTING LONG: BUY {qty} {symbol} @ ~${current_price:,.2f}")
                result = alpaca_post("/v2/orders", {
                    "symbol": symbol, "qty": str(qty),
                    "side": "buy", "type": "market", "time_in_force": "gtc",
                }, key, secret, base)
                log(f"Order: {result.get('id','?')} status={result.get('status')}")
                clean = symbol.replace("/", "")
                trades.setdefault(clean, {}).update({
                    "entry_price": current_price, "peak_pct": 0,
                    "reason": reason, "direction": "long",
                    "entered_at": datetime.now().isoformat(),
                })
            except Exception as e:
                log(f"Long order failed {symbol}: {e}")

    # Execute short signals — short MSTR/COIN as crypto proxy (Alpaca supports stock shorts)
    elif short_signals and slots > 0:
        # Pick one bear-proxy stock per signal slot
        for i, (symbol, reason) in enumerate(short_signals[:slots]):
            stock = BEAR_SHORT_STOCKS[i % len(BEAR_SHORT_STOCKS)]
            # Check not already short this stock
            already_short = any(
                p["symbol"] == stock and float(p.get("qty", 0)) < 0
                for p in all_positions
            )
            if already_short:
                log(f"  Already short {stock}")
                continue
            try:
                # Get stock price from Alpaca
                stock_req = alpaca_get(f"/v2/assets/{stock}", key, secret, base)
                if not stock_req.get("shortable"):
                    log(f"  {stock} not shortable — skipping")
                    continue
                # Use latest quote for sizing
                quote_req = alpaca_get(f"/v2/stocks/{stock}/quotes/latest", key, secret, base)
                ask = float(quote_req.get("quote", {}).get("ap", 0))
                if ask <= 0:
                    log(f"  Could not get {stock} price")
                    continue
                position_usd = portfolio_value * POSITION_SIZE_PCT
                qty = int(position_usd / ask)
                if qty <= 0:
                    continue
                log(f"EXECUTING SHORT: SELL {qty} {stock} @ ~${ask:.2f} (bear proxy for {symbol})")
                result = alpaca_post("/v2/orders", {
                    "symbol": stock, "qty": str(qty),
                    "side": "sell", "type": "market", "time_in_force": "day",
                }, key, secret, base)
                log(f"Short order: {result.get('id','?')} status={result.get('status')}")
                trades.setdefault(f"SHORT_{stock}", {}).update({
                    "entry_price": ask, "peak_pct": 0,
                    "reason": reason, "direction": "short",
                    "crypto_signal": symbol,
                    "entered_at": datetime.now().isoformat(),
                })
            except Exception as e:
                log(f"Short order failed {stock}: {e}")

    save_trade_log(trades)
    log("=== crypto_brain done ===")


if __name__ == "__main__":
    run()
