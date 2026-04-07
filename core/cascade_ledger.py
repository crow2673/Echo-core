#!/usr/bin/env python3
"""
cascade_ledger.py — Tracks four trading sleeves as independent mini-funds
Layer 1: Crypto (24/7) — BTC/ETH/SOL/AVAX
Layer 2: Stock momentum — TSLA/PLTR/COIN/RKLB/IONQ
Layer 3: Stock trend — AAPL/MSFT/NVDA/XOM/JPM
Layer 4: Income/Index — SPY/QQQ/IWM/JEPI/QYLD/PLTW
"""
import json
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
LEDGER_FILE = BASE / "memory/cascade_ledger.json"

LAYER_MAP = {
    "BTC/USD": 1, "ETH/USD": 1, "SOL/USD": 1, "AVAX/USD": 1,
    "BTCUSD": 1, "ETHUSD": 1, "SOLUSD": 1, "AVAXUSD": 1,
    "TSLA": 2, "PLTR": 2, "COIN": 2, "RKLB": 2, "IONQ": 2,
    "SOFI": 2, "MSTR": 2, "HOOD": 2,
    "AAPL": 3, "MSFT": 3, "NVDA": 3, "AMD": 3, "XOM": 3,
    "JPM": 3, "BAC": 3, "CVX": 3,
    "SPY": 4, "QQQ": 4, "IWM": 4, "JEPI": 4, "JEPQ": 4,
    "QYLD": 4, "PLTW": 4, "PLTY": 4, "TSLY": 4, "GLD": 4,
    "BAC": 3, "CVX": 3,
}

LAYER_NAMES = {
    1: "Crypto 24/7",
    2: "Momentum",
    3: "Trend",
    4: "Income/Index"
}

def get_layer(symbol):
    clean = symbol.replace("/", "")
    return LAYER_MAP.get(symbol) or LAYER_MAP.get(clean, 3)

def load_ledger():
    if LEDGER_FILE.exists():
        return json.loads(LEDGER_FILE.read_text())
    return {str(i): {"name": LAYER_NAMES[i], "realized_pl": 0,
                     "total_trades": 0, "wins": 0, "losses": 0,
                     "export_history": []} for i in range(1, 5)}

def save_ledger(ledger):
    LEDGER_FILE.write_text(json.dumps(ledger, indent=2, default=str))

def rebuild_from_logs():
    """Rebuild sleeve ledger from existing trade logs."""
    ledger = load_ledger()
    
    for log_file in [BASE / "memory/trade_log.json",
                     BASE / "memory/crypto_trade_log.json"]:
        if not log_file.exists():
            continue
        trades = json.loads(log_file.read_text())
        for t in trades:
            symbol = t.get("symbol", "")
            layer = get_layer(symbol)
            key = str(layer)
            ledger[key]["total_trades"] += 1
            if t.get("status") == "closed":
                pl_pct = float(t.get("pl_pct", 0))
                cost = float(t.get("price", 0)) * float(t.get("qty", 0))
                pl_dollars = cost * pl_pct / 100
                ledger[key]["realized_pl"] = round(
                    ledger[key]["realized_pl"] + pl_dollars, 2)
                if pl_pct > 0:
                    ledger[key]["wins"] += 1
                else:
                    ledger[key]["losses"] += 1

    save_ledger(ledger)
    return ledger

def print_summary(ledger=None):
    if ledger is None:
        ledger = load_ledger()
    print("\n=== CASCADE SLEEVE LEDGER ===")
    total_pl = 0
    for i in range(1, 5):
        key = str(i)
        s = ledger[key]
        closed = s["wins"] + s["losses"]
        hit = s["wins"] / closed * 100 if closed else 0
        pl = s["realized_pl"]
        total_pl += pl
        print(f"Layer {i} — {s['name']}")
        print(f"  Trades: {s['total_trades']} | Closed: {closed} "
              f"({s['wins']}W {s['losses']}L) | Hit: {hit:.0f}%")
        print(f"  Realized P/L: ${pl:+.2f}")
    print(f"\nTotal realized P/L: ${total_pl:+.2f}")
    print("=============================\n")

def sweep_profits(from_layer, to_layer, amount, reason="scheduled_sweep"):
    """Record a profit sweep from one sleeve to another."""
    ledger = load_ledger()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "from_layer": from_layer,
        "to_layer": to_layer,
        "amount": amount,
        "reason": reason
    }
    ledger[str(from_layer)]["export_history"].append(entry)
    save_ledger(ledger)
    print(f"[ledger] Sweep recorded: Layer {from_layer} → Layer {to_layer} ${amount:.2f}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rebuild":
        ledger = rebuild_from_logs()
        print_summary(ledger)
    else:
        print_summary()
