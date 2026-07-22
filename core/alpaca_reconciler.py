#!/usr/bin/env python3
"""core/alpaca_reconciler.py — Ground-truth P&L reconciler.

Pulls every fill from Alpaca, FIFO-pairs buys/sells per symbol,
assigns each closed trade to the correct sleeve (L1–L4), and
rebuilds cascade_ledger.json + income_knowledge.md from real data.

Runs after every trading cycle via the dispatcher.
This is the source of truth — never trust local trade logs over this.
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LOG = BASE / "logs/alpaca_reconciler.log"
LEDGER_FILE = BASE / "memory/cascade_ledger.json"
INCOME_FILE = BASE / "memory/income_knowledge.md"
STATE_FILE  = BASE / "memory/reconciler_state.json"

# ── Strategy universe maps — imported live from trade_brain so they never drift
def _load_universes():
    try:
        from core.trade_brain import (
            HISTORICAL_TREND_SYMBOLS,
            INDEX_LIST,
            MOMENTUM_LIST,
            TREND_LIST,
        )
        from core.crypto_brain import CRYPTO_WATCHLIST
        crypto  = {s.replace("/", "").upper() for s in CRYPTO_WATCHLIST}
        trend   = set(TREND_LIST) | set(HISTORICAL_TREND_SYMBOLS)
        index   = set(INDEX_LIST)
        momentum = set(MOMENTUM_LIST) | {"COIN", "PYPL", "SQ"}  # extras not yet in brain list
        return crypto, trend, index, momentum
    except Exception as e:
        log(f"warning: could not import from trade_brain/crypto_brain ({e}) — using fallback lists")
        return (
            {"BTCUSD", "ETHUSD", "SOLUSD"},
            {"TLT", "XLF", "XLE", "XLK", "XLV", "XLU", "XLI", "XLP", "XLY", "CVX", "XOM"},
            {"SPY", "QQQ", "IWM", "DIA", "GLD"},
            {"NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "RKLB", "SOFI", "PLTR", "COIN"},
        )

SLEEVE_NAMES = {1: "Crypto 24/7", 2: "Momentum", 3: "Trend", 4: "Income/Index"}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def load_env() -> dict:
    env = {}
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def atomic_write(path: Path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(path)


def get_all_fills(key: str, secret: str, base: str) -> list:
    """Pull every fill from Alpaca, newest-first, all pages."""
    fills = []
    page_token = None
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    while True:
        params = {"activity_type": "FILL", "page_size": "100"}
        if page_token:
            params["page_token"] = page_token
        url = f"{base}/v2/account/activities?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as r:
                batch = json.loads(r.read())
        except Exception as e:
            log(f"fills fetch error: {e}")
            break
        if not batch:
            break
        # Filter out non-fill settlement entries (symbol=None)
        valid = [f for f in batch if f.get("symbol") and f.get("transaction_time")]
        fills.extend(valid)
        if len(batch) < 100:
            break
        page_token = batch[-1].get("id")
    return fills


def normalize_symbol(sym: str) -> str:
    return sym.replace("/", "").replace("-", "").upper()


def assign_sleeve(raw_sym: str, universes: tuple) -> int | None:
    crypto, trend, index, momentum = universes
    sym = normalize_symbol(raw_sym)
    upper = raw_sym.upper()
    if sym in crypto or upper in crypto:
        return 1
    if upper in index:
        return 4
    if upper in trend:
        return 3
    if upper in momentum:
        return 2
    # Unknown symbols must not silently corrupt a sleeve's measured performance.
    log(f"  unknown symbol '{raw_sym}' — excluding from sleeve totals until classified")
    return None


def fifo_pair(fills: list, universes: tuple) -> list:
    """
    Given fills for ONE symbol (sorted oldest-first), FIFO-pair buys to sells.
    Returns list of closed trade dicts with realized P&L.
    """
    buy_queue = []
    closed = []

    for fill in fills:
        side = (fill.get("side") or "").lower()
        try:
            qty   = abs(float(fill.get("qty", 0)))
            price = float(fill.get("price", 0))
        except (TypeError, ValueError):
            continue
        ts = fill.get("transaction_time", "")
        sym = fill.get("symbol", "")

        if side == "buy":
            buy_queue.append({"qty": qty, "price": price, "ts": ts})

        elif side == "sell":
            remaining_sell = qty
            sell_proceeds = 0.0
            cost_basis = 0.0

            while remaining_sell > 1e-8 and buy_queue:
                buy = buy_queue[0]
                matched = min(buy["qty"], remaining_sell)
                sell_proceeds += matched * price
                cost_basis    += matched * buy["price"]
                buy["qty"]    -= matched
                remaining_sell -= matched
                if buy["qty"] < 1e-8:
                    buy_queue.pop(0)

            if cost_basis > 0:
                pl = sell_proceeds - cost_basis
                sleeve = assign_sleeve(sym, universes)
                if sleeve is None:
                    continue
                closed.append({
                    "symbol": sym,
                    "sleeve": sleeve,
                    "qty": qty - remaining_sell,
                    "entry_price": cost_basis / (qty - remaining_sell) if (qty - remaining_sell) > 0 else 0,
                    "exit_price": price,
                    "pl": round(pl, 4),
                    "closed_at": ts,
                })

    return closed


def build_ledger(closed_trades: list) -> dict:
    ledger = {
        str(i): {
            "name": SLEEVE_NAMES[i],
            "realized_pl": 0.0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "export_history": [],
        }
        for i in range(1, 5)
    }

    for t in closed_trades:
        s = str(t["sleeve"])
        ledger[s]["realized_pl"] += t["pl"]
        ledger[s]["total_trades"] += 1
        if t["pl"] >= 0:
            ledger[s]["wins"] += 1
        else:
            ledger[s]["losses"] += 1

    # Round P&L
    for s in ledger.values():
        s["realized_pl"] = round(s["realized_pl"], 2)

    ledger["reconciled_at"] = datetime.now().isoformat()
    ledger["source"] = "alpaca_reconciler"
    return ledger


def update_income_knowledge(ledger: dict, account: dict):
    """Rewrite the Active Income Streams section with real numbers."""
    if not INCOME_FILE.exists():
        log("income_knowledge.md not found — skipping update")
        return

    equity = float(account.get("equity", 0))
    cash   = float(account.get("cash", 0))

    def sleeve_line(n):
        s = ledger.get(str(n), {})
        pl    = s.get("realized_pl", 0)
        total = s.get("total_trades", 0)
        wins  = s.get("wins", 0)
        wr    = f"{int(wins/total*100)}%" if total else "n/a"
        sign  = "+" if pl >= 0 else ""
        return f"**Echo's current status:** ACTIVE — {wr} win rate, {sign}${pl:.0f} realized | paper trading"

    doc = INCOME_FILE.read_text()

    replacements = [
        ("### L1 — Crypto 24/7", "L1"),
        ("### L2 — Momentum Stocks", "L2"),
        ("### L3 — Trend Stocks", "L3"),
        ("### L4 — Income/Index", "L4"),
    ]
    sleeve_map = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}

    lines = doc.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        matched = False
        for header, key in replacements:
            if line.strip().startswith(header.strip()):
                out.append(line)
                # Replace the next **Echo's current status:** line
                i += 1
                while i < len(lines):
                    if lines[i].strip().startswith("**Echo's current status:**"):
                        out.append(sleeve_line(sleeve_map[key]))
                        i += 1
                        matched = True
                        break
                    out.append(lines[i])
                    i += 1
                break
        if not matched:
            out.append(line)
            i += 1

    # Update last updated timestamp
    new_doc = "\n".join(out)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    if "_Last updated:" in new_doc:
        import re
        new_doc = re.sub(r"_Last updated:.*?_", f"_Last updated: {ts}_", new_doc)

    tmp = INCOME_FILE.with_suffix(".tmp")
    tmp.write_text(new_doc)
    tmp.rename(INCOME_FILE)
    log(f"income_knowledge.md updated — equity=${equity:.0f} cash=${cash:.0f}")


def get_account(key, secret, base) -> dict:
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    req = urllib.request.Request(f"{base}/v2/account", headers=headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def log_to_event_ledger(ledger: dict):
    try:
        from core.event_ledger import log_event
        total_pl = sum(ledger.get(str(i), {}).get("realized_pl", 0) for i in range(1, 5))
        log_event("trading", "alpaca_reconciler",
                  f"reconciled: total_pl=${total_pl:+.2f}", score=1.0)
    except Exception:
        pass


def run():
    log("alpaca_reconciler starting")
    env = load_env()
    key    = env.get("ALPACA_API_KEY", "")
    secret = env.get("ALPACA_SECRET_KEY", "")
    base   = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    if not key or not secret:
        log("ALPACA_API_KEY / ALPACA_SECRET_KEY not set — aborting")
        sys.exit(1)

    # Pull account
    try:
        account = get_account(key, secret, base)
        log(f"account: equity=${float(account.get('equity',0)):.2f}  cash=${float(account.get('cash',0)):.2f}")
    except Exception as e:
        log(f"account fetch failed: {e}")
        sys.exit(1)

    # Pull all fills
    log("fetching fills from Alpaca...")
    fills = get_all_fills(key, secret, base)
    log(f"  {len(fills)} fills retrieved")

    if not fills:
        log("no fills — nothing to reconcile")
        return

    # Sort oldest-first for FIFO
    fills.sort(key=lambda f: f.get("transaction_time", ""))

    # Load universes live from trade_brain — picks up any new symbols automatically
    universes = _load_universes()

    # Group by normalized symbol
    by_symbol: dict[str, list] = {}
    for f in fills:
        sym = f.get("symbol", "")
        by_symbol.setdefault(sym, []).append(f)

    # FIFO pair each symbol
    all_closed = []
    for sym, sym_fills in by_symbol.items():
        closed = fifo_pair(sym_fills, universes)
        all_closed.extend(closed)
        if closed:
            log(f"  {sym}: {len(closed)} closed trades  pl=${sum(t['pl'] for t in closed):+.2f}")

    log(f"total closed trades: {len(all_closed)}")

    # Build and save cascade ledger
    ledger = build_ledger(all_closed)
    atomic_write(LEDGER_FILE, ledger)

    total_pl = sum(ledger.get(str(i), {}).get("realized_pl", 0) for i in range(1, 5))
    log(f"cascade ledger rebuilt:")
    for i in range(1, 5):
        s = ledger[str(i)]
        log(f"  L{i} {s['name']}: {s['total_trades']} trades  {s['wins']}W/{s['losses']}L  pl=${s['realized_pl']:+.2f}")
    log(f"  total realized: ${total_pl:+.2f}")
    log(f"  account equity: ${float(account.get('equity',0)):.2f}")

    # Update income_knowledge.md
    update_income_knowledge(ledger, account)

    # Log to event ledger for Echo's learning
    log_to_event_ledger(ledger)

    # Save reconciler state
    state = {
        "last_run": datetime.now().isoformat(),
        "fills_processed": len(fills),
        "closed_trades": len(all_closed),
        "total_pl": total_pl,
        "account_equity": float(account.get("equity", 0)),
    }
    atomic_write(STATE_FILE, state)

    log("reconciler done")


if __name__ == "__main__":
    run()
