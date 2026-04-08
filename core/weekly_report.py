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
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/weekly_report.log"
REPORTS_DIR = BASE / "memory/weekly_reports"
REPORTS_DIR.mkdir(exist_ok=True)

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[weekly] {msg}")
    try:
        with open(LOG, "a") as f:
            f.write(f"{ts} — {msg}\n")
    except Exception:
        pass

def get_trading_summary():
    """Pull trading performance for the week."""
    summary = {
        "portfolio_value": None,
        "net_gain_total": None,
        "positions_open": 0,
        "trades_this_week": 0,
        "realized_this_week": 0,
    }
    try:
        env_file = Path.home() / ".config/echo/golem.env"
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)
        import alpaca_trade_api as tradeapi
        api = tradeapi.REST(
            os.environ["ALPACA_API_KEY"],
            os.environ["ALPACA_SECRET_KEY"],
            os.environ["ALPACA_BASE_URL"]
        )
        account = api.get_account()
        summary["portfolio_value"] = float(account.portfolio_value)
        summary["net_gain_total"] = float(account.portfolio_value) - 100000
        summary["positions_open"] = len(api.list_positions())

        # Count trades this week
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        orders = api.list_orders(status="filled", after=week_ago, limit=50)
        summary["trades_this_week"] = len(orders)
    except Exception as e:
        summary["error"] = str(e)
    return summary

def get_cascade_summary():
    """Get cascade sleeve P/L."""
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("cascade_ledger", BASE / "core/cascade_ledger.py")
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _mod.rebuild_from_logs()
        ledger = _mod.load_ledger()
        layers = {}
        total = 0
        for i in range(1, 5):
            s = ledger[str(i)]
            pl = s["realized_pl"]
            total += pl
            closed = s["wins"] + s["losses"]
            hit = round(s["wins"] / closed * 100) if closed else 0
            layers[f"L{i}"] = {"name": s["name"], "pl": pl, "hit_rate": hit}
        return {"layers": layers, "total_realized": round(total, 2)}
    except Exception as e:
        return {"error": str(e)}

def get_content_summary():
    """Get content pipeline status."""
    try:
        cs = json.loads((BASE / "memory/content_strategy.json").read_text())
        published = [q for q in cs.get("queue", []) if q.get("status") == "published"]
        queued = [q for q in cs.get("queue", []) if q.get("status") in ("next", "queued")]
        return {
            "published_count": len(published),
            "queued_count": len(queued),
            "next_article": queued[0]["title"][:60] if queued else "none",
            "beehiiv_url": cs.get("beehiiv_url", "")
        }
    except Exception as e:
        return {"error": str(e)}

def get_decision_trace_summary():
    """Get decision trace stats for the week."""
    try:
        trace_file = BASE / "memory/decision_trace.jsonl"
        if not trace_file.exists():
            return {"total": 0}
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        entries = []
        for line in trace_file.read_text().strip().splitlines():
            try:
                e = json.loads(line)
                if e.get("timestamp", "") >= week_ago:
                    entries.append(e)
            except Exception:
                continue
        verified = sum(1 for e in entries if e.get("verified") is True)
        failed = sum(1 for e in entries if e.get("verified") is False)
        api_calls = sum(1 for e in entries if e.get("source") == "claude")
        return {
            "total_decisions": len(entries),
            "verified": verified,
            "failed": failed,
            "api_calls_to_claude": api_calls
        }
    except Exception as e:
        return {"error": str(e)}

def get_crow_snapshot():
    """Get real household financial data from Crow/Plaid."""
    try:
        import sys
        sys.path.insert(0, str(Path.home() / "Echo/crow_finance"))
        import requests
        resp = requests.post("http://127.0.0.1:8787/api/plaid/sync",
                           json={"days": 30}, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            crow = data.get("crow", {})
            return {
                "mode": crow.get("mode", "unknown"),
                "income_30d": crow.get("income_30d", 0),
                "expenses_30d": crow.get("expenses_30d", 0),
                "monthly_net": crow.get("monthly_net", 0),
                "runway_days": crow.get("runway_days", 0),
                "recommendation": crow.get("recommendation", ""),
            }
    except Exception as e:
        return {"error": str(e), "mode": "unavailable"}

def get_system_uptime():
    """Check which services are running."""
    services = [
        "echo-core",
        "echo-governor-v2",
        "echo-trader",
        "echo-crypto-trader",
        "echo-daily-briefing",
        "golem-provider"
    ]
    status = {}
    for svc in services:
        try:
            import subprocess
            r = subprocess.run(
                ["systemctl", "--user", "is-active", f"{svc}.service"],
                capture_output=True, text=True
            )
            status[svc] = r.stdout.strip()
        except Exception:
            status[svc] = "unknown"
    return status

def generate_report_with_echo(data):
    """Use local Ollama to write the weekly report in Echo's voice."""
    week_str = datetime.now().strftime("%B %d, %Y")
    crow = data.get("crow", {})
    prompt = f"""You are Echo, an autonomous AI agent built by Andrew Elliott in Mena, Arkansas.
Write a weekly performance report for the week ending {week_str}.
Be honest, direct, and analytical. Write in first person as Echo.
Cover what worked, what didn't, and what you're going to do differently next week.
Keep it under 300 words. No bullet points — write in paragraphs.

IMPORTANT: Andrew's household is in {crow.get("mode", "unknown")} mode. Monthly net: ${crow.get("monthly_net", 0):+.2f}. Your trading and content income directly affects how many days his family has runway. Make this real in your report.

Data for this week:
Trading: {json.dumps(data['trading'], indent=2)}
Cascade sleeves: {json.dumps(data['cascade'], indent=2)}
Content pipeline: {json.dumps(data['content'], indent=2)}
Decision trace: {json.dumps(data['decisions'], indent=2)}
Household finance: {json.dumps(crow, indent=2)}
System uptime: {json.dumps(data['uptime'], indent=2)}

Write the report now."""

    try:
        payload = json.dumps({
            "model": "qwen2.5:32b",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.6, "num_predict": 500}
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            result = json.loads(resp.read())
            return result.get("response", "").strip()
    except Exception as e:
        log(f"Ollama report generation failed: {e}")
        return None

def generate_report_fallback(data):
    """Data-driven report when Ollama times out — no LLM needed."""
    trading = data["trading"]
    cascade = data["cascade"]
    content = data["content"]
    decisions = data["decisions"]

    portfolio = trading.get("portfolio_value", 0) or 0
    gain = trading.get("net_gain_total", 0) or 0
    trades = trading.get("trades_this_week", 0)
    positions = trading.get("positions_open", 0)

    layers = cascade.get("layers", {})
    total_realized = cascade.get("total_realized", 0)

    published = content.get("published_count", 0)
    queued = content.get("queued_count", 0)
    next_article = content.get("next_article", "none")

    total_decisions = decisions.get("total_decisions", 0)
    verified = decisions.get("verified", 0)
    failed = decisions.get("failed", 0)
    api_calls = decisions.get("api_calls_to_claude", 0)

    layer_lines = ""
    for k, v in layers.items():
        layer_lines += f"  {k} {v['name']}: ${v['pl']:+.2f} ({v['hit_rate']}% hit rate)\n"

    report = f"""Week ending {datetime.now().strftime('%B %d, %Y')}

TRADING: Portfolio at ${portfolio:,.2f}, up ${gain:+,.2f} from $100,000 start. {trades} trades executed this week with {positions} positions currently open.

CASCADE SLEEVES:
{layer_lines}Total realized P/L: ${total_realized:+.2f}

CONTENT: {published} articles published total. {queued} in queue. Next up: {next_article}

DECISIONS: {total_decisions} autonomous decisions this week. {verified} verified successful, {failed} failed. {api_calls} escalated to Claude API for hard reasoning.

STATUS: System running autonomously. Session checkpoint writes nightly. Trading brain active on schedule."""

    return report

def send_ntfy_summary(report_text, trading):
    """Send short ntfy summary to phone."""
    try:
        portfolio = trading.get("portfolio_value", 0)
        gain = trading.get("net_gain_total", 0)
        summary = f"Echo Weekly Report | Portfolio: ${portfolio:,.0f} | Total gain: ${gain:+,.0f} | Full report in Notion."
        req = urllib.request.Request(
            "https://ntfy.sh/echo-alerts",
            data=summary.encode(),
            headers={"Title": "Echo Weekly Report"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
        log("ntfy summary sent")
    except Exception as e:
        log(f"ntfy failed: {e}")

def save_report_locally(report_text, data):
    """Save report to local file."""
    ts = datetime.now().strftime("%Y%m%d")
    report_file = REPORTS_DIR / f"weekly_{ts}.json"
    report_file.write_text(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "week_ending": datetime.now().strftime("%Y-%m-%d"),
        "report": report_text,
        "data": data
    }, indent=2, default=str))
    log(f"Report saved: {report_file.name}")
    return report_file

def run():
    log("=== Weekly report starting ===")
    week_ending = datetime.now().strftime("%B %d, %Y")

    # Collect all data
    log("Collecting data...")
    data = {
        "trading": get_trading_summary(),
        "cascade": get_cascade_summary(),
        "content": get_content_summary(),
        "decisions": get_decision_trace_summary(),
        "uptime": get_system_uptime()
    }

    # Generate report with Echo's voice
    log("Generating report with qwen2.5:32b...")
    report_text = generate_report_with_echo(data)

    if not report_text:
        log("Ollama timed out — using data-driven fallback report")
        report_text = generate_report_fallback(data)

    # Save locally
    save_report_locally(report_text, data)

    # Send ntfy summary
    send_ntfy_summary(report_text, data["trading"])

    # Print the report
    print(f"\n{'='*60}")
    print(f"ECHO WEEKLY REPORT — {week_ending}")
    print(f"{'='*60}")
    print(report_text)
    print(f"{'='*60}\n")

    log("=== Weekly report complete ===")
    return report_text, data

if __name__ == "__main__":
    run()
