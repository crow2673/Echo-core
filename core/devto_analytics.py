#!/usr/bin/env python3
"""
core/devto_analytics.py
Reads dev.to article performance after publish.
Feeds outcome data back to Echo's feedback loop.
"""
import json
import urllib.request
from datetime import datetime
from pathlib import Path

home = Path.home()
BASE = home / "Echo"
CONFIG = home / ".config/echo/golem.env"
LOG = BASE / "logs/analytics.log"


def load_api_key():
    if CONFIG.exists():
        for line in CONFIG.read_text().splitlines():
            if line.startswith("DEV_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def fetch_articles(api_key):
    req = urllib.request.Request(
        "https://dev.to/api/articles/me",
        headers={
            "User-Agent": "Echo/1.0 (personal AI assistant; dev.to/crow)",
            "api-key": api_key,
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def fetch_article_stats(article_id, api_key):
    req = urllib.request.Request(
        f"https://dev.to/api/articles/{article_id}",
        headers={"api-key": api_key},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} — {msg}", flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"{ts} — {msg}\n")


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

    results = []
    total_views = 0
    best = {"title": "none", "views": 0}

    for a in articles:
        title = a.get("title", "untitled")
        views = a.get("page_views_count", 0)
        reactions = a.get("positive_reactions_count", 0)
        comments = a.get("comments_count", 0)
        log(f"{title[:50]} | views:{views} reactions:{reactions} comments:{comments}")
        results.append({
            "title": title,
            "views": views,
            "reactions": reactions,
            "comments": comments,
            "published_at": a.get("published_at", ""),
            "updated_at": datetime.now().isoformat(),
        })
        total_views += views
        if views > best["views"]:
            best = {"title": title, "views": views}

    log(f"total — views:{total_views} reactions:{sum(r['reactions'] for r in results)} articles:{len(results)}")

    (BASE / "memory/devto_analytics.json").write_text(
        json.dumps(results, indent=2)
    )

    if best["title"] != "none":
        log(f"feedback injected: best article was '{best['title'][:50]}'")
        try:
            from core.event_ledger import log_event
            log_event("content", "devto_analytics", f"best: {best['title'][:80]} ({best['views']} views)", score=1.0)
        except Exception:
            pass


if __name__ == "__main__":
    run()
