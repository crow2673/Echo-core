#!/usr/bin/env python3
"""
core/devto_analytics.py
Reads dev.to article performance after publish.
Feeds outcome data back to Echo's feedback loop.
"""
import json
import urllib.request
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "Echo"
CONFIG = Path.home() / ".config/echo/golem.env"
LOG = BASE / "logs/analytics.log"

def load_api_key():
    if CONFIG.exists():
        for line in CONFIG.read_text().splitlines():
            if line.startswith("DEV_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None

def fetch_articles(api_key):
    req = urllib.request.Request(
        "https://dev.to/api/articles/me",
        headers={"api-key": api_key, "User-Agent": "Echo/1.0 (personal AI assistant; dev.to/crow)"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def fetch_article_stats(api_key, article_id):
    req = urllib.request.Request(
        f"https://dev.to/api/articles/{article_id}",
        headers={"api-key": api_key}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} — {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def run():
    api_key = load_api_key()
    if not api_key:
        log("ERROR: no DEV_API_KEY found")
        return

    log("fetching article analytics")
    
    try:
        articles = fetch_articles(api_key)
    except Exception as e:
        log(f"ERROR fetching articles: {e}")
        return

    if not articles:
        log("no articles found")
        return

    total_views = 0
    total_reactions = 0
    report = []

    for a in articles:
        aid = a.get("id")
        title = a.get("title", "untitled")[:50]
        views = a.get("page_views_count", 0)
        reactions = a.get("positive_reactions_count", 0)
        comments = a.get("comments_count", 0)
        published = a.get("published_at", "")[:10]
        url = a.get("url", "")

        total_views += views
        total_reactions += reactions

        entry = {
            "id": aid,
            "title": title,
            "views": views,
            "reactions": reactions,
            "comments": comments,
            "published": published,
            "url": url,
            "checked_at": datetime.now().isoformat()
        }
        report.append(entry)
        log(f"{title} | views:{views} reactions:{reactions} comments:{comments}")

    # Save report
    report_file = BASE / "memory/devto_analytics.json"
    report_file.write_text(json.dumps(report, indent=2))

    log(f"total — views:{total_views} reactions:{total_reactions} articles:{len(articles)}")

    # Feed best performing article back to feedback loop
    if report:
        best = max(report, key=lambda x: x["views"])
        feedback_entry = {
            "id": f"analytics_{datetime.now().strftime('%Y%m%d')}",
            "suggestion": f"Best performing article: '{best['title']}' with {best['views']} views. Write more content on similar topics to drive traffic.",
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "source": "devto_analytics",
            "confidence": 0.85
        }
        fb_log = BASE / "memory/feedback_log.json"
        fb_data = json.loads(fb_log.read_text())
        # Don't duplicate today's entry
        today = datetime.now().strftime("%Y%m%d")
        existing = [s for s in fb_data if s.get("id", "").startswith(f"analytics_{today}")]
        if not existing:
            fb_data.append(feedback_entry)
            fb_log.write_text(json.dumps(fb_data, indent=2))
            log(f"feedback injected: best article was '{best['title']}'")

    # Run performance tracker after analytics
    try:
        from core.devto_performance_tracker import run as track
        track()
    except Exception as e:
        log(f"performance tracker error: {e}")

if __name__ == "__main__":
    run()
