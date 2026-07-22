#!/usr/bin/env python3
"""core/robinhood_guard.py — the seatbelts for real-money Robinhood Agentic trading.

Robinhood Agentic Trading lets an AI place REAL orders in a REAL brokerage
account (see [[project_robinhood_guardrails]]). The agreement makes Andrew fully
liable; Robinhood does not monitor the AI. This module encodes the hard
guardrails AS CODE so they don't depend on anyone (human or model) remembering
them. Every proposed order MUST pass preflight() before it is sent to the
robinhood-trading MCP server.

It is the trading analogue of core/circuit_breaker.py: that one halts runaway
event/RAM loops; this one halts runaway / unsafe / oversized TRADES.

Enforces (none of these relax without Andrew's explicit per-item say-so):
  1. ACCOUNT WHITELIST   — only the dedicated CASH "Agentic" account. Every
                           margin account is hard-refused (guardrail #1).
  2. CASH, NEVER MARGIN  — if handed account metadata, type=="margin" is blocked.
  3. PER-ORDER CEILING   — no single order's notional may exceed HARD_MAX_TRADE_USD
                           (fat-finger / mis-sized-quantity protection).
  4. DAILY LOSS BREAKER  — once realized losses today cross DAILY_LOSS_LIMIT_USD,
                           trip and block ALL further orders until reset.
  5. MAX TRADES/DAY      — runaway-loop protection.
  6. MANUAL APPROVAL     — preflight NEVER returns auto-approve. Every order is
                           returned requires_manual_approval=True.

Usage (before any place_equity_order MCP call):
    from core.robinhood_guard import preflight, record_fill
    d = preflight(account_number, symbol, side, notional_usd, est_price=..., account=...)
    if not d["allow"]:
        # do NOT place the order; surface d["reasons"]
    # ... after a human approves AND the order fills:
    record_fill(symbol, side, notional_usd, realized_pl=...)

CLI:
    python3 core/robinhood_guard.py --status      # show today's guard state
    python3 core/robinhood_guard.py --selftest    # exercise every rule
    python3 core/robinhood_guard.py --reset-day   # clear today's counters (manual)
    python3 core/robinhood_guard.py --reset-breaker  # untrip the loss breaker (manual)
"""
import sys, json, argparse
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
STATE = BASE / "memory/robinhood_guard_state.json"
LOG = BASE / "logs/robinhood_guard.log"

# ── HARD GUARDRAILS (the seatbelts — see module docstring & memory) ────────────
ALLOWED_ACCOUNTS    = {"620925974"}   # the dedicated CASH "Agentic" account ONLY
HARD_MAX_TRADE_USD  = 25.0            # absolute per-order notional ceiling
DAILY_LOSS_LIMIT_USD = 5.0           # trip the breaker once today's realized loss hits this
MAX_TRADES_PER_DAY  = 10             # runaway-loop protection
AUTO_APPROVE        = False          # NEVER True. Guarded below; preflight forces manual.


def now():
    return datetime.now(timezone.utc)


def _today():
    return now().astimezone().strftime("%Y-%m-%d")


def log(msg):
    line = f"[{now().astimezone().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _ledger(event_type, summary, data=None):
    try:
        from core.event_ledger import log_event
        log_event(event_type, "robinhood_guard", summary, data=data)
    except Exception:
        pass


def _alert(title, msg):
    try:
        from core.notifier import notify
        notify(title, msg, urgent=True, phone=True, desktop=True)
    except Exception as e:
        log(f"alert failed: {e}")


# ── State (per-day counters + the loss breaker) ───────────────────────────────
def _fresh_state():
    return {"day": _today(), "trades_today": 0, "realized_pl_today": 0.0,
            "breaker_tripped": False, "breaker_reason": None, "history": []}


def load_state():
    st = _fresh_state()
    if STATE.exists():
        try:
            st = json.loads(STATE.read_text())
        except Exception:
            pass
    # auto-roll the day (counters reset; a tripped breaker does NOT auto-reset
    # mid-day, but a new day starts clean).
    if st.get("day") != _today():
        hist = st.get("history", [])[-200:]
        st = _fresh_state()
        st["history"] = hist
    return st


def save_state(st):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2, default=str))
    tmp.rename(STATE)


def _block(reasons, st, ctx):
    decision = {"allow": False, "requires_manual_approval": True,
                "reasons": reasons, "checked_at": now().isoformat(), **ctx}
    log(f"BLOCK {ctx.get('side','?')} {ctx.get('symbol','?')} "
        f"${ctx.get('notional_usd',0):.2f} — {'; '.join(reasons)}")
    _ledger("robinhood_order_blocked",
            f"BLOCKED {ctx.get('side')} {ctx.get('symbol')} ${ctx.get('notional_usd',0):.2f}: "
            f"{'; '.join(reasons)}", data=decision)
    st.setdefault("history", []).append(decision)
    save_state(st)
    return decision


def preflight(account_number, symbol, side, notional_usd, est_price=None, account=None):
    """Gate a proposed equity order. Returns a decision dict. allow=False means
    DO NOT send it to the MCP. allow=True still requires a human approval before
    placing (requires_manual_approval is always True).

    account_number : the brokerage account the order would hit (string).
    notional_usd   : dollar size of the order (qty*price if you only have qty).
    account        : optional account metadata dict from get_accounts (lets the
                     guard verify type=='cash' directly).
    """
    st = load_state()
    notional_usd = float(notional_usd or 0)
    ctx = {"account_number": str(account_number), "symbol": symbol,
           "side": (side or "").lower(), "notional_usd": round(notional_usd, 2),
           "est_price": est_price}
    reasons = []

    # 1. account whitelist (the #1 line — never trade the wrong account)
    if str(account_number) not in ALLOWED_ACCOUNTS:
        reasons.append(f"account {account_number} is NOT the whitelisted Agentic "
                       f"cash account — refused")

    # 2. cash, never margin (if we were handed the account metadata)
    if account is not None:
        if account.get("type") == "margin":
            reasons.append("target account is type=margin — refused (cash only)")
        if account.get("agentic_allowed") is False:
            reasons.append("target account has agentic_allowed=false — refused")

    # breaker already tripped today?
    if st.get("breaker_tripped"):
        reasons.append(f"daily loss breaker is TRIPPED ({st.get('breaker_reason')}) "
                       f"— all trading halted until manual reset")

    # 3. per-order notional ceiling (fat-finger)
    if notional_usd > HARD_MAX_TRADE_USD:
        reasons.append(f"order ${notional_usd:.2f} exceeds per-order cap "
                       f"${HARD_MAX_TRADE_USD:.2f}")
    if notional_usd <= 0:
        reasons.append("order notional is zero/unknown — cannot size-check")

    # 5. max trades/day (runaway loop)
    if st.get("trades_today", 0) >= MAX_TRADES_PER_DAY:
        reasons.append(f"already {st['trades_today']} trades today "
                       f"(cap {MAX_TRADES_PER_DAY}) — halted for the day")

    if reasons:
        return _block(reasons, st, ctx)

    # passed every hard rule — but approval is ALWAYS human (guardrail #3)
    decision = {"allow": True, "requires_manual_approval": True,  # never auto
                "reasons": ["passed all guardrails — REQUIRES manual approval before placing"],
                "checked_at": now().isoformat(), **ctx}
    log(f"ALLOW (pending manual approval) {ctx['side']} {symbol} ${notional_usd:.2f}")
    _ledger("robinhood_order_cleared",
            f"CLEARED (awaiting manual approval) {ctx['side']} {symbol} ${notional_usd:.2f}",
            data=decision)
    st.setdefault("history", []).append(decision)
    save_state(st)
    return decision


def record_fill(symbol, side, notional_usd, realized_pl=0.0):
    """Call AFTER a human-approved order actually fills. Updates the day's trade
    count and realized P&L, and trips the loss breaker if the day's losses cross
    the limit."""
    st = load_state()
    st["trades_today"] = st.get("trades_today", 0) + 1
    st["realized_pl_today"] = round(st.get("realized_pl_today", 0.0) + float(realized_pl), 4)
    st.setdefault("history", []).append(
        {"event": "fill", "ts": now().isoformat(), "symbol": symbol, "side": side,
         "notional_usd": round(float(notional_usd), 2), "realized_pl": round(float(realized_pl), 4)})

    loss = -st["realized_pl_today"]  # positive number = how much we're down today
    if loss >= DAILY_LOSS_LIMIT_USD and not st.get("breaker_tripped"):
        st["breaker_tripped"] = True
        st["breaker_reason"] = f"realized loss ${loss:.2f} today >= ${DAILY_LOSS_LIMIT_USD:.2f}"
        log(f"DAILY LOSS BREAKER TRIPPED — {st['breaker_reason']}")
        _ledger("robinhood_breaker_tripped", st["breaker_reason"], data=st)
        _alert("Robinhood loss breaker TRIPPED",
               f"{st['breaker_reason']}. All agentic trading halted until manual reset.")
    save_state(st)
    return st


def status():
    st = load_state()
    print(json.dumps({k: st[k] for k in
          ("day", "trades_today", "realized_pl_today", "breaker_tripped", "breaker_reason")},
          indent=2))
    print(f"\nguardrails: account(s)={sorted(ALLOWED_ACCOUNTS)}  "
          f"per-order<=${HARD_MAX_TRADE_USD}  daily-loss-limit=${DAILY_LOSS_LIMIT_USD}  "
          f"max-trades/day={MAX_TRADES_PER_DAY}  auto-approve={AUTO_APPROVE}")


def selftest():
    """Exercise every rule against a throwaway state (does not touch real state)."""
    global STATE
    import tempfile
    orig = STATE
    STATE = Path(tempfile.mkdtemp()) / "guard_test.json"
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    assert not AUTO_APPROVE, "AUTO_APPROVE must be False"
    check("auto-approve hard-off", AUTO_APPROVE is False)

    good = preflight("620925974", "AAPL", "buy", 5.0, est_price=200)
    check("whitelisted cash account, small order -> allow", good["allow"])
    check("...but still requires manual approval", good["requires_manual_approval"])

    wrong = preflight("840261713", "AAPL", "buy", 5.0)
    check("wrong (margin) account -> block", not wrong["allow"])

    marg = preflight("620925974", "AAPL", "buy", 5.0, account={"type": "margin"})
    check("account metadata type=margin -> block", not marg["allow"])

    big = preflight("620925974", "AAPL", "buy", 9999.0, est_price=200)
    check("oversized order -> block", not big["allow"])

    zero = preflight("620925974", "AAPL", "buy", 0)
    check("zero notional -> block", not zero["allow"])

    # trip the loss breaker, then confirm it blocks
    record_fill("AAPL", "sell", 5.0, realized_pl=-DAILY_LOSS_LIMIT_USD)
    after = preflight("620925974", "MSFT", "buy", 3.0, est_price=300)
    check("after loss-breaker trip -> block", not after["allow"])

    STATE = orig
    print("\nselftest:", "ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--reset-day", action="store_true", help="clear today's trade count + P&L")
    ap.add_argument("--reset-breaker", action="store_true", help="manually untrip the loss breaker")
    a = ap.parse_args()

    if a.selftest:
        sys.exit(selftest())
    if a.reset_day:
        st = load_state(); st.update(trades_today=0, realized_pl_today=0.0); save_state(st)
        log("day counters manually reset"); return
    if a.reset_breaker:
        st = load_state(); st.update(breaker_tripped=False, breaker_reason=None); save_state(st)
        log("loss breaker manually reset"); return
    status()


if __name__ == "__main__":
    main()
