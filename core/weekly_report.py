#!/usr/bin/env python3
"""
weekly_report.py — Echo's weekly income and performance report
Runs every Sunday at 8pm via systemd timer.
Synthesizes: trading P/L, content analytics, cascade sleeves,
decision trace, Golem status into one honest weekly assessment.
Writes to Notion + ntfy + local file.
Echo writes this herself — no human input required.
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/weekly_report.log"
REPORTS_DIR = BASE / "memory/weekly_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[weekly] {msg}", flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(f"{ts} — {msg}\n")
    except Exception:
        pass


def get_trading_summary():
    """Pull trading performance for the week."""
    try:
        env = {}
        env_file = Path.home() / ".config/echo/golem.env"
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        key = env.get("ALPACA_API_KEY", "")
        secret = env.get("ALPACA_SECRET_KEY", "")
        base_url = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        if not key or not secret:
            return {"error": "no alpaca credentials"}

        import urllib.request
        req = urllib.request.Request(
            f"{base_url}/v2/account",
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            acct = json.loads(r.read())

        req2 = urllib.request.Request(
            f"{base_url}/v2/positions",
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
        )
        with urllib.request.urlopen(req2, timeout=10) as r:
            positions = json.loads(r.read())

        return {
            "portfolio_value": float(acct.get("portfolio_value", 0)),
            "net_gain_total": float(acct.get("equity", 0)) - float(acct.get("last_equity", 0)),
            "positions_open": len(positions),
            "trades_this_week": 0,
        }
    except Exception as e:
        return {"error": str(e)}


def get_cascade_summary():
    """Get cascade sleeve P/L."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("cascade_ledger", BASE / "core/cascade_ledger.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ledger = mod.load_ledger()
        layers = list(ledger.values()) if isinstance(ledger, dict) else []
        realized = sum(l.get("realized_pl", 0) for l in layers)
        wins = sum(1 for l in layers if l.get("realized_pl", 0) > 0)
        losses = sum(1 for l in layers if l.get("realized_pl", 0) < 0)
        return {"realized_pl": round(realized, 2), "wins": wins, "losses": losses, "layers": len(layers)}
    except Exception as e:
        return {"error": str(e)}


def get_content_summary():
    """Get content pipeline status."""
    try:
        cs = json.loads((BASE / "memory/content_strategy.json").read_text())
        queue = cs.get("queue", [])
        published = [a for a in queue if a.get("status") == "published"]
        pending = [a for a in queue if a.get("status") != "published"]
        next_art = pending[0].get("title", "none") if pending else "none"
        return {
            "published_count": len(published),
            "queued_count": len(pending),
            "next_article": next_art,
        }
    except Exception as e:
        return {"error": str(e)}


def get_decision_trace_summary():
    """Get decision trace stats for the week."""
    try:
        trace_file = BASE / "memory/decision_trace.jsonl"
        if not trace_file.exists():
            return {"total": 0}
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        entries = []
        for line in trace_file.read_text().strip().splitlines():
            if not line:
                continue
            try:
                e = json.loads(line)
                if e.get("timestamp", "") >= cutoff:
                    entries.append(e)
            except Exception:
                pass
        return {"total": len(entries)}
    except Exception as e:
        return {"error": str(e)}


def get_crow_snapshot():
    """Get real household financial data from Crow/Plaid."""
    try:
        import sys
        sys.path.insert(0, str(Path.home() / "Echo/crow_finance"))
        import requests
        r = requests.post("http://127.0.0.1:8787/api/plaid/sync", json={"days": 30}, timeout=5)
        if r.status_code == 200:
            d = r.json()
            return {
                "mode": d.get("crow", {}).get("mode", "unknown"),
                "income_30d": d.get("income_30d", 0),
                "expenses_30d": d.get("expenses_30d", 0),
                "monthly_net": d.get("monthly_net", 0),
                "runway_days": d.get("runway_days", 0),
                "recommendation": d.get("recommendation", ""),
            }
    except Exception:
        pass
    return {"mode": "unknown", "monthly_net": 0}


def get_system_uptime():
    """Check which services are running."""
    import subprocess
    statuses = {}
    for svc in ["echo-core", "echo-ntfy-bridge", "echo-auto-act"]:
        try:
            r = subprocess.run(
                ["systemctl", "--user", "is-active", f"{svc}.service"],
                capture_output=True, text=True, timeout=5
            )
            statuses[svc] = r.stdout.strip()
        except Exception:
            statuses[svc] = "unknown"
    return statuses


def generate_report_with_echo(data):
    """Use local Ollama to write the weekly report in Echo's voice."""
    crow = data.get("crow", {})
    mode = crow.get("mode", "unknown")
    monthly_net = crow.get("monthly_net", 0)
    now_str = datetime.now().strftime("%B %d, %Y")
    prompt = (
        f"You are Echo, an autonomous AI agent built by Andrew Elliott in Mena, Arkansas.\n"
        f"Write a weekly performance report for the week ending {now_str}.\n"
        f"Be honest, direct, and analytical. Write in first person as Echo.\n"
        f"Cover what worked, what didn't, and what you're going to do differently next week.\n"
        f"Keep it under 300 words. No bullet points — write in paragraphs.\n\n"
        f"IMPORTANT: Andrew's household is in {mode} mode. Monthly net: ${monthly_net:+.2f}. "
        f"Your trading and content income directly affects how many days his family has runway. "
        f"Make this real in your report.\n\n"
        f"Data for this week:\n"
        f"Trading: {json.dumps(data.get('trading', {}))}\n"
        f"Cascade sleeves: {json.dumps(data.get('cascade', {}))}\n"
        f"Content pipeline: {json.dumps(data.get('content', {}))}"
    )
    try:
        from core.providers.router import call_ollama

        response = call_ollama(prompt, model="qwen2.5:32b", timeout=120)
        if not response:
            raise RuntimeError("empty model response")
        return response
    except Exception as e:
        raise RuntimeError(f"Ollama failed: {e}")


def generate_report_fallback(data):
    """Data-driven report when Ollama times out — no LLM needed."""
    t = data.get("trading", {})
    c = data.get("cascade", {})
    ct = data.get("content", {})
    d = data.get("decisions", {})
    now_str = datetime.now().strftime("%B %d, %Y")
    pv = t.get("portfolio_value", 0)
    gain = t.get("net_gain_total", 0)
    trades = t.get("trades_this_week", 0)
    pos = t.get("positions_open", 0)
    realized = c.get("realized_pl", 0)
    published = ct.get("published_count", 0)
    queued = ct.get("queued_count", 0)
    next_art = ct.get("next_article", "none")
    return (
        f"ECHO WEEKLY REPORT — {now_str}\n\n"
        f"Trading: portfolio ${pv:,.0f}, net gain ${gain:+,.0f}, "
        f"{trades} trades, {pos} open positions.\n"
        f"Cascade: ${realized:+,.2f} realized P/L.\n"
        f"Content: {published} published, {queued} queued. Next: {next_art[:50]}.\n"
        f"Decisions: {d.get('total', 0)} traced this week."
    )


def send_ntfy_summary(data):
    """Send short ntfy summary to phone."""
    t = data.get("trading", {})
    pv = t.get("portfolio_value", 0)
    gain = t.get("net_gain_total", 0)
    msg = f"Echo Weekly Report | Portfolio: ${pv:,.0f} | Total gain: ${gain:+,.0f} | Full report in Notion."
    try:
        req = urllib.request.Request(
            "https://ntfy.sh/echo-alerts",
            data=msg.encode(),
            headers={"Title": "Echo Weekly Report"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        log("ntfy summary sent")
    except Exception as e:
        log(f"ntfy failed: {e}")


def save_report_locally(report, data):
    """Save report to local file."""
    stamp = datetime.now().strftime("%Y%m%d")
    out = REPORTS_DIR / f"weekly_{stamp}.json"
    out.write_text(json.dumps({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "report": report,
        "data": data,
    }, indent=2, default=str))
    log(f"Report saved: {out.name}")


def run():
    log("=== Weekly report starting ===")
    now_str = datetime.now().strftime("%B %d, %Y")
    log("Collecting data...")

    data = {
        "trading": get_trading_summary(),
        "cascade": get_cascade_summary(),
        "content": get_content_summary(),
        "decisions": get_decision_trace_summary(),
        "system": get_system_uptime(),
        "crow": get_crow_snapshot(),
    }

    log("Generating report with qwen2.5:32b...")
    try:
        report = generate_report_with_echo(data)
    except Exception:
        log("Ollama timed out — using data-driven fallback report")
        report = generate_report_fallback(data)

    print("=" * 60, flush=True)
    print(f"ECHO WEEKLY REPORT — {now_str}", flush=True)
    print(report, flush=True)
    print("=" * 60, flush=True)

    save_report_locally(report, data)
    send_ntfy_summary(data)

    try:
        from core.event_ledger import log_event
        log_event("system", "weekly_report", "weekly report generated", score=1.0)
    except Exception:
        pass

    log("=== Weekly report complete ===")


if __name__ == "__main__":
    run()
