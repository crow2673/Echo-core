#!/usr/bin/env python3
"""
strategy_scraper.py
Scrapes known trading strategies from public sources.
Stores findings in semantic memory for Echo to reason about.
"""
import json
import requests
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
MEMORY = BASE / "memory/trading_strategies.json"

def scrape_reddit_algotrading():
    """Pull top posts from r/algotrading via Reddit JSON API"""
    strategies = []
    urls = [
        "https://www.reddit.com/r/algotrading/top.json?limit=25&t=year",
        "https://www.reddit.com/r/algotrading/search.json?q=strategy+backtest&sort=top&limit=25",
    ]
    headers = {"User-Agent": "Echo/1.0 strategy research bot"}
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            data = r.json()
            for post in data["data"]["children"]:
                p = post["data"]
                if p.get("score", 0) > 100:
                    strategies.append({
                        "source": "reddit_algotrading",
                        "title": p["title"],
                        "score": p["score"],
                        "url": f"https://reddit.com{p['permalink']}",
                        "summary": p.get("selftext", "")[:500],
                        "scraped_at": datetime.now().isoformat()
                    })
        except Exception as e:
            print(f"Error scraping {url}: {e}")
    return strategies

def scrape_investopedia_strategies():
    """Known high-level strategies to seed Echo's knowledge"""
    return [
        {"source": "seed", "title": "Moving Average Crossover", "summary": "Buy when 50-day MA crosses above 200-day MA (golden cross). Sell when 50-day crosses below 200-day (death cross). Simple trend following. Works best in trending markets, fails in sideways markets."},
        {"source": "seed", "title": "RSI Mean Reversion", "summary": "Buy when RSI drops below 30 (oversold). Sell when RSI rises above 70 (overbought). Works best in ranging markets. Fails in strong trends."},
        {"source": "seed", "title": "Bollinger Band Squeeze", "summary": "When bands narrow (low volatility), a breakout is coming. Buy on breakout above upper band, sell on breakdown below lower band. Good for volatile assets."},
        {"source": "seed", "title": "MACD Crossover", "summary": "Buy when MACD line crosses above signal line. Sell when MACD crosses below signal line. Momentum indicator. Lags price but filters noise."},
        {"source": "seed", "title": "Volume Price Trend", "summary": "High volume on up days, low volume on down days = bullish. High volume on down days = bearish. Volume confirms price moves."},
        {"source": "seed", "title": "Opening Range Breakout", "summary": "First 30 minutes sets the range. Buy breakout above range high, sell breakdown below range low. Day trading strategy, close all positions by end of day."},
        {"source": "seed", "title": "Momentum / Relative Strength", "summary": "Buy top performing assets from last 3-12 months. Sell bottom performers. Rebalance monthly. Strong academic backing. Works across stocks, crypto, commodities."},
    ]

if __name__ == "__main__":
    print("Scraping strategies...")
    strategies = scrape_investopedia_strategies()
    reddit = scrape_reddit_algotrading()
    strategies.extend(reddit)
    MEMORY.write_text(json.dumps(strategies, indent=2))
    print(f"Saved {len(strategies)} strategies to memory")
    for s in strategies[:5]:
        print(f"  [{s['source']}] {s['title']}")
