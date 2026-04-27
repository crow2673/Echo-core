#!/usr/bin/env python3
"""
core/command_handler.py
Command handler for Echo core daemon.
"""
from __future__ import annotations
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
EVENTS_FILE = BASE / "echo_events.ndjson"


def _tail_events(n=20):
    if not EVENTS_FILE.exists():
        return []
    lines = EVENTS_FILE.read_text().splitlines()
    results = []
    for line in lines[-n:]:
        line = line.strip()
        if line:
            try:
                results.append(json.loads(line))
            except Exception:
                pass
    return results


def handle_command(text: str, memory: dict) -> str:
    """Handle slash-commands from the user. Returns reply string."""
    cmd = text.strip().lower()

    if cmd in ("/status", "status", "/health"):
        try:
            from core.self_awareness import build_self_awareness_block
            return build_self_awareness_block()
        except Exception as e:
            return f"Status check failed: {e}"

    if cmd in ("/events", "/log"):
        events = _tail_events(10)
        if not events:
            return "No recent events."
        lines = []
        for e in events[-10:]:
            ts = e.get("ts", e.get("timestamp", "?"))[:16]
            etype = e.get("type", "?")
            src = e.get("source", e.get("src", ""))
            msg = e.get("message", e.get("msg", ""))
            lines.append(f"[{ts}] {etype}/{src}: {msg[:80]}")
        return "\n".join(lines)

    if cmd in ("/memory", "/mem"):
        exchanges = memory.get("exchanges", [])
        return f"Memory: {len(exchanges)} exchanges stored."

    if cmd in ("/leads", "/fiverr"):
        try:
            leads_file = BASE / "memory/demand_leads.json"
            if not leads_file.exists():
                return "No leads file found."
            leads = json.loads(leads_file.read_text())
            top = [l for l in leads if l.get("score", 0) >= 7][:5]
            if not top:
                return "No high-score leads right now."
            lines = [f"Score {l['score']}: {l['title'][:60]}" for l in top]
            return "Top Fiverr leads:\n" + "\n".join(lines)
        except Exception as e:
            return f"Leads error: {e}"

    if cmd in ("/trades", "/positions"):
        try:
            trade_log = BASE / "memory/trade_log.json"
            crypto_log = BASE / "memory/crypto_trade_log.json"
            parts = []
            if trade_log.exists():
                trades = json.loads(trade_log.read_text())
                open_pos = [s for s, t in trades.items() if isinstance(t, dict) and not t.get("closed_at")]
                parts.append(f"Stocks: {len(open_pos)} open positions")
            if crypto_log.exists():
                ctrades = json.loads(crypto_log.read_text())
                copen = [s for s, t in ctrades.items() if isinstance(t, dict) and not t.get("closed_at")]
                parts.append(f"Crypto: {len(copen)} open positions")
            return "\n".join(parts) if parts else "No trade logs found."
        except Exception as e:
            return f"Trades error: {e}"

    if cmd.startswith("/help"):
        return (
            "Echo commands:\n"
            "  /status   — system health snapshot\n"
            "  /events   — recent event log\n"
            "  /leads    — top Fiverr leads\n"
            "  /trades   — open trading positions\n"
            "  /memory   — memory stats\n"
            "  /help     — this message"
        )

    return None  # not a command
