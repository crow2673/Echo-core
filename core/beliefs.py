#!/usr/bin/env python3
"""
core/beliefs.py — Echo's living strategy confidence tracker

Every trading signal Echo uses has a confidence level that updates
from real outcomes. Starts at 0.65 (slightly positive prior).
Each closed trade moves confidence ~15% toward the actual result.

Confidence → position scalar:
  >= 0.70  → 1.0x  (full position)
  0.50-0.69 → 0.75x (three-quarter)
  0.30-0.49 → 0.50x (half)
  < 0.30   → None  (skip — signal has failed too often)

Read by:  trade_brain.py, crypto_brain.py before sizing positions
Updated by: outcome_reviewer.py after each closed trade
"""
import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
BELIEFS_FILE = BASE / "memory/beliefs.json"

DEFAULTS = {
    "rsi_below35_above_ma20": {"label": "RSI < 35 with price above MA20 (trend strategy)", "confidence": 0.65},
    "ma20_above_ma50_rsi_below60": {"label": "MA20 > MA50 uptrend with RSI < 60 (trend strategy)", "confidence": 0.65},
    "momentum_5d_surge": {"label": "5-day momentum > 3% with volume surge (momentum strategy)", "confidence": 0.65},
    "crypto_rsi_below35_above_ma10": {"label": "Crypto RSI < 35 with price above MA10 (crypto strategy)", "confidence": 0.65},
    "crypto_momentum_6h": {"label": "Crypto 6h momentum > 2.5% with RSI < 65 (crypto strategy)", "confidence": 0.65},
}


def _load():
    if BELIEFS_FILE.exists():
        try:
            return json.loads(BELIEFS_FILE.read_text())
        except Exception:
            pass
    return {k: dict(v) for k, v in DEFAULTS.items()}


def _save(beliefs):
    BELIEFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = BELIEFS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(beliefs, indent=2))
    tmp.rename(BELIEFS_FILE)


def get_confidence(signal_key: str) -> float:
    beliefs = _load()
    return beliefs.get(signal_key, DEFAULTS.get(signal_key, {"confidence": 0.65}))["confidence"]


def get_position_scalar(signal_key: str) -> float | None:
    c = get_confidence(signal_key)
    if c >= 0.70:
        return 1.0
    if c >= 0.50:
        return 0.75
    if c >= 0.30:
        return 0.50
    return None


def record_outcome(signal_key: str, won: bool):
    beliefs = _load()
    if signal_key not in beliefs:
        beliefs[signal_key] = {"label": signal_key, "confidence": 0.65}
    c = beliefs[signal_key]["confidence"]
    target = 1.0 if won else 0.0
    beliefs[signal_key]["confidence"] = round(c + 0.15 * (target - c), 4)
    beliefs[signal_key]["last_updated"] = datetime.now().isoformat()
    beliefs[signal_key]["last_result"] = "win" if won else "loss"
    _save(beliefs)


def signal_key_for(strategy: str, symbol: str = "") -> str:
    strategy = strategy.lower()
    if "crypto" in strategy or "btc" in symbol.lower() or "eth" in symbol.lower():
        if "momentum" in strategy:
            return "crypto_momentum_6h"
        return "crypto_rsi_below35_above_ma10"
    if "momentum" in strategy:
        return "momentum_5d_surge"
    if "trend" in strategy or "ma" in strategy:
        return "ma20_above_ma50_rsi_below60"
    return "rsi_below35_above_ma20"


def get_all_beliefs() -> dict:
    return _load()


def get_low_confidence_signals() -> list:
    beliefs = _load()
    return [k for k, v in beliefs.items() if v.get("confidence", 0.65) < 0.40]


def summary_report() -> str:
    beliefs = _load()
    lines = []
    for k, v in beliefs.items():
        c = v.get("confidence", 0.65)
        scalar = get_position_scalar(k)
        label = v.get("label", k)[:50]
        lines.append(f"  {label}: {c:.2f} → {scalar}x")
    return "\n".join(lines)
