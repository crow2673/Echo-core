#!/usr/bin/env python3
"""core/experiment_10usd.py — Echo's $10 / 24h "grow it fast" experiment.

A self-contained, capital-capped trader that proves the real-money path on the
paper account first. Swap the paper key for a live AK key and the exact same
code runs on real $10.

Mandate (Andrew, 2026-06-11): take $10, don't lose it, grow it as fast as
possible in 24h, flatten before the deadline. Take-profit is ADAPTIVE —
a volatility-scaled trailing stop, not a fixed %.

Design:
  • Hard $10 budget cap — never deploys more than it has (cash semantics).
  • Crypto only (BTC/ETH/SOL) — trades the full 24h window, no settlement delays.
  • One best idea at a time, momentum-picked; re-enters to compound while time remains.
  • Adaptive exit:
      - trailing stop activates after a small gain, then rides the winner;
        trail distance = clamp(1.5 x recent bar volatility) per coin.
      - hard floor preserves capital if it goes wrong.
      - forced flatten near the 24h deadline.
  • Every decision logged with reasoning -> reviewable diff against baseline.

State of truth: memory/experiment_10usd_state.json
Own P&L is tracked from actual fills, isolated from the main paper portfolio.

Run:
  python3 core/experiment_10usd.py --once     # one cycle (safe to repeat)
  python3 core/experiment_10usd.py --run       # loop until deadline
  python3 core/experiment_10usd.py --status     # print state, no action
  python3 core/experiment_10usd.py --flatten    # emergency: sell + stop
"""
import sys, json, time, argparse, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
STATE = BASE / "memory/experiment_10usd_state.json"
LOG = BASE / "logs/experiment_10usd.log"
DATA = "https://data.alpaca.markets/v1beta3/crypto/us"

# ── Knobs ────────────────────────────────────────────────────────────────────
BUDGET            = 10.00          # starting capital (USD)
UNIVERSE          = ["BTC/USD", "ETH/USD", "SOL/USD"]
RUN_HOURS         = 24
POLL_SECONDS      = 60
ENTRY_MOMENTUM_MIN = 0.15          # require >0.15% momentum (last ~2h) to enter
TRAIL_ACTIVATE    = 0.025          # start trailing only after +2.5% (don't whipsaw on entry noise)
TRAIL_MIN         = 0.010          # trailing stop never tighter than 1.0%
TRAIL_MAX         = 0.060          # ...nor wider than 6.0%
TRAIL_VOL_MULT    = 1.5            # trail distance = mult x recent bar volatility
HARD_FLOOR        = -0.15          # exit if down 15% from entry (capital preservation)
DEADLINE_BUFFER_MIN = 5            # force flatten this many minutes before deadline
MIN_BUDGET        = 2.00           # stop trading if budget falls below this (too small to matter)


def now():
    return datetime.now(timezone.utc)


def log(msg):
    line = f"[{now().astimezone().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def load_env():
    env = {}
    for line in (Path.home() / ".config/echo/golem.env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


ENV = load_env()
# ISOLATION: the $10 experiment uses DEDICATED live keys (ALPACA_LIVE_*) if present,
# so taking it real NEVER flips the main trading system — that keeps the paper
# ALPACA_* key. Drop ALPACA_LIVE_API_KEY / ALPACA_LIVE_SECRET_KEY into golem.env and
# ONLY this $10 test trades real money; everything else stays on paper.
if ENV.get("ALPACA_LIVE_API_KEY") and ENV.get("ALPACA_LIVE_SECRET_KEY"):
    KEY = ENV["ALPACA_LIVE_API_KEY"]
    SEC = ENV["ALPACA_LIVE_SECRET_KEY"]
    TRADE_BASE = ENV.get("ALPACA_LIVE_BASE_URL", "https://api.alpaca.markets")
else:
    KEY = ENV["ALPACA_API_KEY"]
    SEC = ENV["ALPACA_SECRET_KEY"]
    TRADE_BASE = ENV.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
HEAD = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SEC, "Content-Type": "application/json"}
IS_LIVE = KEY.startswith("AK")
# Paper crypto matching engine is unreliable (orders park in 'new'). For the paper
# dry run we simulate fills against live prices so the 24h behavioral test is clean.
# A live (AK) key sends REAL orders — live crypto fills work.
SIM_FILLS = not IS_LIVE
SLIPPAGE  = 0.001   # 10 bps adverse on each side — keeps the sim honest


def _get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=HEAD)))


def _post(path, body):
    req = urllib.request.Request(TRADE_BASE + path, data=json.dumps(body).encode(),
                                 headers=HEAD, method="POST")
    return json.load(urllib.request.urlopen(req))


# ── Market data ───────────────────────────────────────────────────────────────
def latest_prices():
    syms = ",".join(UNIVERSE)
    d = _get(f"{DATA}/latest/trades?symbols={syms}")
    return {s: t["p"] for s, t in d.get("trades", {}).items()}


def momentum_and_vol():
    """Return {symbol: (return_pct, vol_pct)} over the last ~2h of 15Min bars."""
    syms = ",".join(UNIVERSE)
    d = _get(f"{DATA}/bars?symbols={syms}&timeframe=15Min&limit=8")
    out = {}
    for s, bars in d.get("bars", {}).items():
        if len(bars) >= 3:
            ret = (bars[-1]["c"] / bars[0]["c"] - 1) * 100
            vol = sum(abs(b["h"] - b["l"]) / b["c"] for b in bars) / len(bars) * 100
            out[s] = (ret, vol)
    return out


# ── Orders ────────────────────────────────────────────────────────────────────
def _await_fill(order_id, tries=20):
    for _ in range(tries):
        o = _get(f"{TRADE_BASE}/v2/orders/{order_id}")
        if o.get("status") == "filled":
            return float(o["filled_qty"]), float(o["filled_avg_price"])
        if o.get("status") in ("canceled", "rejected", "expired"):
            return None, None
        time.sleep(1.5)
    return None, None


def buy(symbol, notional, price):
    if SIM_FILLS:
        fill = price * (1 + SLIPPAGE)          # pay a touch up
        return round(notional / fill, 9), fill
    o = _post("/v2/orders", {"symbol": symbol, "notional": f"{notional:.2f}",
                             "side": "buy", "type": "market", "time_in_force": "gtc"})
    return _await_fill(o["id"])


def sell(symbol, qty, price):
    if SIM_FILLS:
        fill = price * (1 - SLIPPAGE)          # sell a touch down
        return qty, fill
    o = _post("/v2/orders", {"symbol": symbol, "qty": f"{qty:.9f}",
                             "side": "sell", "type": "market", "time_in_force": "gtc"})
    return _await_fill(o["id"])


# ── State ─────────────────────────────────────────────────────────────────────
def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    st = {
        "mode": "LIVE-REAL-MONEY" if IS_LIVE else "PAPER-DRY-RUN (simulated fills)",
        "started_at": now().isoformat(),
        "deadline": (now() + timedelta(hours=RUN_HOURS)).isoformat(),
        "status": "running",
        "start_budget": BUDGET,
        "budget": BUDGET,           # cash available for next entry
        "realized_pl": 0.0,
        "trades": [],
        "position": None,
        "log": [],
    }
    save_state(st)
    log(f"experiment initialized — {st['mode']} — budget ${BUDGET:.2f} — deadline {st['deadline']}")
    return st


def save_state(st):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2, default=str))
    tmp.rename(STATE)


def note(st, msg):
    st["log"].append({"ts": now().isoformat(), "msg": msg})
    log(msg)


def equity(st, prices):
    eq = st["budget"]
    p = st["position"]
    if p:
        px = prices.get(p["symbol"], p["entry_price"])
        eq += p["qty"] * px
    return eq


# ── Core logic ────────────────────────────────────────────────────────────────
def adaptive_trail(vol_pct):
    raw = TRAIL_VOL_MULT * (vol_pct / 100.0)
    return max(TRAIL_MIN, min(TRAIL_MAX, raw))


def try_enter(st, prices, mom):
    candidates = [(s, r, v) for s, (r, v) in mom.items() if r >= ENTRY_MOMENTUM_MIN and s in prices]
    if not candidates:
        note(st, f"flat — no coin clears momentum>{ENTRY_MOMENTUM_MIN}% "
                 f"({', '.join(f'{s}:{r:+.2f}%' for s,(r,v) in mom.items())}); waiting")
        return
    candidates.sort(key=lambda x: x[1], reverse=True)
    sym, ret, vol = candidates[0]
    spend = round(st["budget"], 2)
    note(st, f"ENTER {sym} — momentum {ret:+.2f}%, vol {vol:.2f}%, deploying ${spend:.2f}")
    qty, fill = buy(sym, spend, prices[sym])
    if qty is None:
        note(st, f"entry FAILED for {sym} (no fill) — staying flat")
        return
    st["position"] = {"symbol": sym, "qty": qty, "entry_price": fill,
                      "entry_time": now().isoformat(), "peak_price": fill,
                      "notional": spend, "entry_vol": vol}
    st["budget"] = round(st["budget"] - spend, 2)
    note(st, f"FILLED buy {sym} qty={qty:.8f} @ ${fill:,.2f}")


def manage(st, prices, mom, force=False, reason="deadline"):
    p = st["position"]
    px = prices.get(p["symbol"])
    if px is None:
        note(st, f"no price for {p['symbol']} — holding")
        return
    p["peak_price"] = max(p["peak_price"], px)
    gain = px / p["entry_price"] - 1
    dd_from_peak = px / p["peak_price"] - 1
    vol = mom.get(p["symbol"], (0, p.get("entry_vol", 1.0)))[1]
    trail = adaptive_trail(vol)

    exit_reason = None
    if force:
        exit_reason = reason
    elif gain <= HARD_FLOOR:
        exit_reason = "hard_floor"
    elif gain >= TRAIL_ACTIVATE and dd_from_peak <= -trail:
        exit_reason = f"trailing_stop(trail={trail*100:.1f}%)"

    if not exit_reason:
        note(st, f"HOLD {p['symbol']} @ ${px:,.2f} | gain {gain*100:+.2f}% "
                 f"| peak ${p['peak_price']:,.2f} (dd {dd_from_peak*100:+.2f}%) "
                 f"| trail {trail*100:.1f}% armed={'Y' if gain>=TRAIL_ACTIVATE else 'N'}")
        return

    qty, fill = sell(p["symbol"], p["qty"], px)
    if qty is None:
        note(st, f"EXIT order failed for {p['symbol']} — will retry next cycle")
        return
    proceeds = qty * fill
    pl = proceeds - p["notional"]
    st["realized_pl"] = round(st["realized_pl"] + pl, 4)
    st["budget"] = round(st["budget"] + proceeds, 2)
    st["trades"].append({
        "symbol": p["symbol"], "entry": p["entry_price"], "exit": fill,
        "qty": qty, "pl": round(pl, 4), "reason": exit_reason,
        "entry_time": p["entry_time"], "exit_time": now().isoformat(),
    })
    note(st, f"EXIT {p['symbol']} @ ${fill:,.2f} [{exit_reason}] | "
             f"P&L ${pl:+.4f} | budget now ${st['budget']:.2f}")
    st["position"] = None


def cycle(st):
    deadline = datetime.fromisoformat(st["deadline"])
    prices = latest_prices()
    mom = momentum_and_vol()
    near_deadline = now() >= deadline - timedelta(minutes=DEADLINE_BUFFER_MIN)

    if near_deadline:
        if st["position"]:
            note(st, "DEADLINE reached — flattening")
            manage(st, prices, mom, force=True, reason="deadline")
        st["status"] = "done"
        eq = equity(st, prices)
        note(st, f"EXPERIMENT DONE — final equity ${eq:.2f} "
                 f"(start ${st['start_budget']:.2f}, P&L ${eq-st['start_budget']:+.2f}, "
                 f"{len(st['trades'])} trades)")
        save_state(st)
        return False

    if st["position"]:
        manage(st, prices, mom)
    elif st["budget"] >= MIN_BUDGET:
        try_enter(st, prices, mom)
    else:
        note(st, f"budget ${st['budget']:.2f} < ${MIN_BUDGET} floor — standing down until deadline")

    save_state(st)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--flatten", action="store_true")
    a = ap.parse_args()

    st = load_state()

    if a.status:
        prices = latest_prices()
        eq = equity(st, prices)
        print(json.dumps({k: st[k] for k in ("mode", "status", "budget", "realized_pl",
              "position", "deadline")}, indent=2, default=str))
        print(f"live equity (mark-to-market): ${eq:.2f} | P&L ${eq-st['start_budget']:+.2f}")
        return

    if a.flatten:
        prices = latest_prices()
        if st["position"]:
            manage(st, prices, momentum_and_vol(), force=True, reason="manual_flatten")
        st["status"] = "done"
        save_state(st)
        log("manual flatten complete — experiment stopped")
        return

    if st["status"] == "done":
        log("experiment already done — nothing to do")
        return

    if a.run:
        log(f"--run loop started ({st['mode']}); polling every {POLL_SECONDS}s")
        while True:
            try:
                if not cycle(st):
                    break
            except urllib.error.HTTPError as e:
                log(f"HTTP error: {e.code} {e.read()[:200]}")
            except Exception as e:
                log(f"cycle error: {e}")
            st = load_state()
            time.sleep(POLL_SECONDS)
        log("--run loop ended")
    else:  # --once (default)
        cycle(st)


if __name__ == "__main__":
    main()
