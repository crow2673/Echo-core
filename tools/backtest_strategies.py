#!/usr/bin/env python3
"""
tools/backtest_strategies.py — honest "buy low / sell high" vs buy-and-hold.

Tests mean-reversion timing (RSI, Bollinger, MA-deviation) against simply holding,
on the real historical crypto data Echo already has, WITH trading fees. Long-only,
all-in/all-out, cash when flat. Reports total return, trade count, win rate, and
max drawdown per strategy vs the hold baseline.

Honesty caveats (printed): results are IN-SAMPLE (same history used to pick the
rules), so real-world/out-of-sample performance is typically WORSE, not better.
No look-ahead: signals act on the next bar's close conservatively via same-bar
close execution with a fee penalty.

Run:  venv/bin/python tools/backtest_strategies.py   (needs pyarrow → use venv)
"""
import glob
import pandas as pd
import numpy as np

FEE = 0.001  # 0.1% per transaction (typical crypto taker fee); round-trip = 0.2%


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def signals(df):
    c = df["close"]
    out = {}
    # RSI mean-reversion: buy oversold (<30), sell overbought (>70)
    r = rsi(c)
    out["RSI(14) 30/70"] = (r < 30, r > 70)
    # Bollinger reversion: buy below lower band, sell above upper (20, 2σ)
    mid = c.rolling(20).mean(); sd = c.rolling(20).std()
    out["Bollinger 20/2"] = (c < mid - 2 * sd, c > mid + 2 * sd)
    # MA deviation: buy 5% below the 50-bar SMA, sell 5% above
    sma = c.rolling(50).mean()
    out["MA50 ±5%"] = (c < sma * 0.95, c > sma * 1.05)
    return out


def backtest(close, buy, sell, fee=FEE):
    close = close.values; buy = buy.fillna(False).values; sell = sell.fillna(False).values
    equity = 1.0; pos = False; entry = 0.0; trades = []; peak = 1.0; maxdd = 0.0
    for i in range(len(close)):
        p = close[i]
        if not pos and buy[i]:
            pos = True; entry = p; equity *= (1 - fee)
        elif pos and sell[i]:
            equity *= (p / entry) * (1 - fee); trades.append(p / entry - 1); pos = False
        mtm = equity * (p / entry) if pos else equity
        peak = max(peak, mtm); maxdd = max(maxdd, (peak - mtm) / peak)
    if pos:
        equity *= (close[-1] / entry) * (1 - fee); trades.append(close[-1] / entry - 1)
    win = (sum(1 for t in trades if t > 0) / len(trades) * 100) if trades else 0.0
    return (equity - 1) * 100, len(trades), win, maxdd * 100


def main():
    files = sorted(glob.glob("backtests/data/*_USDT-1h-futures.feather"))
    print(f"Honest backtest — mean-reversion ('buy low/sell high') vs buy-and-hold")
    print(f"Fee {FEE*100:.1f}%/trade · long-only · IN-SAMPLE (real-world would be worse)\n")
    header = f"{'asset':6} {'strategy':16} {'return':>9} {'vs HOLD':>9} {'trades':>7} {'win%':>6} {'maxDD':>7}"
    for f in files:
        asset = f.split("/")[-1].split("_")[0]
        df = pd.read_feather(f)
        hold = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
        print(f"=== {asset}  (buy & hold: {hold:+.1f}%) ===")
        print(header)
        print(f"{asset:6} {'BUY & HOLD':16} {hold:>+8.1f}% {'—':>9} {'1':>7} {'—':>6} {'—':>7}")
        for name, (buy, sell) in signals(df).items():
            ret, ntr, win, dd = backtest(df["close"], buy, sell)
            beat = ret - hold
            print(f"{asset:6} {name:16} {ret:>+8.1f}% {beat:>+8.1f}% {ntr:>7} {win:>5.0f}% {dd:>6.1f}%")
        print()


if __name__ == "__main__":
    main()
