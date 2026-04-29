#!/usr/bin/env python3
"""
cascade_ledger.py — Tracks four trading sleeves as independent mini-funds
Layer 1: Crypto (24/7) — BTC/ETH/SOL/AVAX
Layer 2: Stock momentum — TSLA/PLTR/COIN/RKLB/IONQ
Layer 3: Stock trend — AAPL/MSFT/NVDA/XOM/JPM
Layer 4: Income/Index — SPY/QQQ/IWM/JEPI/QYLD/PLTW
"""
import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LEDGER_FILE = BASE / "memory/cascade_ledger.json"

LAYERS = {
    1: {"name": "Crypto", "symbols": ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD"]},
    2: {"name": "Momentum", "symbols": ["TSLA", "PLTR", "COIN", "RKLB", "IONQ"]},
    3: {"name": "Trend", "symbols": ["AAPL", "MSFT", "NVDA", "XOM", "JPM"]},
    4: {"name": "Income", "symbols": ["SPY", "QQQ", "IWM", "JEPI", "QYLD", "PLTW"]},
}


def get_layer(layer_num: int) -> dict:
    return LAYERS.get(layer_num, {})


def load_ledger() -> dict:
    if LEDGER_FILE.exists():
        try:
            return json.loads(LEDGER_FILE.read_text())
        except Exception:
            pass
    return {str(i): {"name": v["name"], "realized_pl": 0.0, "wins": 0, "losses": 0, "trades": []}
            for i, v in LAYERS.items()}


def save_ledger(ledger: dict):
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(ledger, indent=2, default=str))
    tmp.rename(LEDGER_FILE)


def rebuild_from_logs() -> dict:
    """Rebuild ledger from trade_log.json and crypto_trade_log.json."""
    ledger = load_ledger()
    try:
        trade_log = BASE / "memory/trade_log.json"
        if trade_log.exists():
            trades = json.loads(trade_log.read_text())
            for sym, t in trades.items():
                if not isinstance(t, dict) or not t.get("closed_at"):
                    continue
                pl = t.get("realized_pl", 0.0)
                layer_key = "2" if sym in LAYERS[2]["symbols"] else "3"
                if sym in LAYERS[4]["symbols"]:
                    layer_key = "4"
                layer = ledger.setdefault(layer_key, {"realized_pl": 0.0, "wins": 0, "losses": 0})
                layer["realized_pl"] = round(layer.get("realized_pl", 0) + pl, 2)
                if pl > 0:
                    layer["wins"] = layer.get("wins", 0) + 1
                else:
                    layer["losses"] = layer.get("losses", 0) + 1

        crypto_log = BASE / "memory/crypto_trade_log.json"
        if crypto_log.exists():
            ctrades = json.loads(crypto_log.read_text())
            for sym, t in ctrades.items():
                if not isinstance(t, dict) or not t.get("closed_at"):
                    continue
                pl = t.get("realized_pl", 0.0)
                layer = ledger.setdefault("1", {"realized_pl": 0.0, "wins": 0, "losses": 0})
                layer["realized_pl"] = round(layer.get("realized_pl", 0) + pl, 2)
                if pl > 0:
                    layer["wins"] = layer.get("wins", 0) + 1
                else:
                    layer["losses"] = layer.get("losses", 0) + 1
    except Exception:
        pass
    return ledger


def reconcile_from_alpaca(key, secret):
    """Reconcile ledger against live Alpaca positions."""
    ledger = load_ledger()
    # No-op if credentials not available
    if not key or not secret:
        return ledger
    try:
        import urllib.request
        base_url = "https://paper-api.alpaca.markets"
        req = urllib.request.Request(
            f"{base_url}/v2/positions",
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            positions = json.loads(r.read())
        for pos in positions:
            sym = pos.get("symbol", "")
            unreal = float(pos.get("unrealized_pl", 0))
            for layer_num, layer_info in LAYERS.items():
                if sym in layer_info["symbols"]:
                    layer_key = str(layer_num)
                    ledger.setdefault(layer_key, {})["unrealized_pl"] = round(
                        ledger[layer_key].get("unrealized_pl", 0) + unreal, 2
                    )
    except Exception:
        pass
    return ledger


def get_summary() -> dict:
    return load_ledger()


def print_summary():
    ledger = load_ledger()
    print("=== Cascade Ledger ===")
    total = 0.0
    for i in range(1, 5):
        layer = ledger.get(str(i), {})
        name = LAYERS[i]["name"]
        pl = layer.get("realized_pl", 0.0)
        wins = layer.get("wins", 0)
        losses = layer.get("losses", 0)
        print(f"  L{i} {name}: ${pl:+.2f} ({wins}W/{losses}L)")
        total += pl
    print(f"  TOTAL: ${total:+.2f}")


def sweep_profits(threshold=50.0):
    """Mark excess profits in each layer for rebalancing."""
    ledger = load_ledger()
    swept = {}
    for key, layer in ledger.items():
        pl = layer.get("realized_pl", 0.0)
        if pl >= threshold:
            swept[key] = pl
    return swept


if __name__ == "__main__":
    print_summary()
