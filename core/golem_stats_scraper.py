#!/usr/bin/env python3
"""
core/golem_stats_scraper.py
Queries local yagna market API to benchmark Echo's pricing against other providers.
"""
import json
import requests
import subprocess
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/golem_recommendations.log"
FEEDBACK = BASE / "memory/feedback_log.json"

YAGNA_API = "http://localhost:7465"
MY_CPU_PRICE = 0.00015
MY_DURATION_PRICE = 0.00005

def get_app_key():
    try:
        result = subprocess.run(
            ["yagna", "app-key", "list", "--json"],
            capture_output=True, text=True
        )
        keys = json.loads(result.stdout)
        return keys[0].get("key", "")
    except:
        key_path = BASE / "memory/app_key.path"
        if key_path.exists():
            return key_path.read_text().strip()
        return ""

def fetch_market_offers(app_key):
    headers = {"Authorization": f"Bearer {app_key}"}
    r = requests.get(f"{YAGNA_API}/market-api/v1/offers", headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()

def analyze_offers(offers):
    cpu_prices = []
    duration_prices = []
    for offer in offers:
        props = offer.get("properties", {})
        coeffs = props.get("golem.com.pricing.model.linear.coeffs", [])
        if len(coeffs) >= 2 and coeffs[0] > 0:
            cpu_prices.append(coeffs[0])
            duration_prices.append(coeffs[1])
    if not cpu_prices:
        return None
    cpu_prices.sort()
    n = len(cpu_prices)
    return {
        "total_offers": n,
        "cpu_min": cpu_prices[0],
        "cpu_median": cpu_prices[n // 2],
        "cpu_max": cpu_prices[-1],
        "cpu_bottom25": cpu_prices[n // 4],
        "cpu_top25": cpu_prices[3 * n // 4],
    }

def log_recommendation(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG, "a") as f:
        f.write(f"{ts} — {msg}\n")
    print(msg)

def inject_feedback(suggestion):
    if not FEEDBACK.exists():
        data = []
    else:
        data = json.loads(FEEDBACK.read_text())
    data.append({
        "id": f"golem_pricing_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "suggestion": suggestion,
        "status": "pending",
        "source": "golem_stats_scraper",
        "confidence": 0.8,
        "created_at": datetime.now().isoformat()
    })
    FEEDBACK.write_text(json.dumps(data, indent=2))

def run():
    try:
        app_key = get_app_key()
        if not app_key:
            log_recommendation("Could not get yagna app key.")
            return

        offers = fetch_market_offers(app_key)
        # Filter out our own offers
        other_offers = [o for o in offers if o.get("providerId") != "0x400ec5a2ff6afbd42d169a86ae0cac5dcd4db296"]

        if not other_offers:
            log_recommendation("No other provider offers visible in market right now.")
            return

        stats = analyze_offers(other_offers)
        if not stats:
            log_recommendation("Could not parse offer pricing data.")
            return

        log_recommendation(
            f"Market: {stats['total_offers']} other offers. "
            f"CPU price — min: {stats['cpu_min']:.5f}, median: {stats['cpu_median']:.5f}, max: {stats['cpu_max']:.5f}. "
            f"Echo CPU: {MY_CPU_PRICE:.5f}"
        )

        if MY_CPU_PRICE > stats["cpu_top25"]:
            msg = f"Echo is in top 25% most expensive. Consider lowering CPU price to {stats['cpu_median']:.5f} GLM/s."
            log_recommendation(msg)
            inject_feedback(f"adjust Golem pricing — lower cpu price from {MY_CPU_PRICE} to {stats['cpu_median']:.5f}")
        elif MY_CPU_PRICE < stats["cpu_bottom25"]:
            msg = f"Echo is in bottom 25% cheapest. Could raise to {stats['cpu_median']:.5f} and still be competitive."
            log_recommendation(msg)
        else:
            log_recommendation("Echo pricing is within competitive range. No adjustment needed.")

    except Exception as e:
        log_recommendation(f"Scraper error: {e}")

if __name__ == "__main__":
    run()
