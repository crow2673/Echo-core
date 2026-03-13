#!/usr/bin/env python3
"""
Echo RSS Monitor — Internet awareness tier 1
Fetches trending content from dev.to, Hacker News, r/LocalLLaMA,
Golem blog, and Ollama releases.
Stores summaries in memory/world_context.md for Echo to read during reasoning.
Runs daily via echo-rss-monitor.timer
"""
import json, sys, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime
try:
    from xml.etree import ElementTree as ET
except ImportError:
    ET = None

BASE = Path(__file__).resolve().parents[1]
OUTPUT = BASE / "memory/world_context.md"
LOG = BASE / "logs/rss_monitor.log"

def log(msg):
    LOG.parent.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def fetch(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Echo/1.0 RSS Monitor"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        log(f"fetch failed {url}: {e}")
        return None

def parse_rss(xml_text, limit=5):
    """Parse RSS/Atom feed, return list of (title, link, summary)"""
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = []
        # RSS 2.0
        for item in root.findall(".//item")[:limit]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()[:200]
            items.append((title, link, desc))
        # Atom
        if not items:
            for entry in root.findall(".//atom:entry", ns)[:limit]:
                title = entry.findtext("atom:title", "", ns).strip()
                link = entry.find("atom:link", ns)
                href = link.get("href", "") if link is not None else ""
                summary = entry.findtext("atom:summary", "", ns).strip()[:200]
                items.append((title, href, summary))
        return items
    except Exception as e:
        log(f"parse error: {e}")
        return []

def fetch_devto_trending():
    """Dev.to top articles via API"""
    try:
        url = "https://dev.to/api/articles?top=7&per_page=5"
        req = urllib.request.Request(url, headers={"User-Agent": "Echo/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            articles = json.loads(r.read())
        return [(a["title"], a["url"], f"{a.get('positive_reactions_count',0)} reactions, {a.get('reading_time_minutes',0)}min read") for a in articles[:5]]
    except Exception as e:
        log(f"devto failed: {e}")
        return []

def fetch_hackernews():
    """Hacker News top stories via API"""
    try:
        with urllib.request.urlopen("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10) as r:
            ids = json.loads(r.read())[:5]
        items = []
        for sid in ids:
            try:
                with urllib.request.urlopen(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=10) as r:
                    story = json.loads(r.read())
                title = story.get("title", "")
                url = story.get("url", f"https://news.ycombinator.com/item?id={sid}")
                score = story.get("score", 0)
                items.append((title, url, f"{score} points"))
            except Exception:
                pass
        return items
    except Exception as e:
        log(f"hackernews failed: {e}")
        return []

def fetch_reddit_localllama():
    """r/LocalLLaMA top posts via JSON API (no auth needed)"""
    try:
        url = "https://www.reddit.com/r/LocalLLaMA/hot.json?limit=5"
        req = urllib.request.Request(url, headers={"User-Agent": "Echo/1.0 RSS Monitor"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        posts = data["data"]["children"]
        return [(p["data"]["title"], f"https://reddit.com{p['data']['permalink']}", f"{p['data']['score']} upvotes") for p in posts[:5]]
    except Exception as e:
        log(f"reddit failed: {e}")
        return []

def fetch_golem_blog():
    return parse_rss(fetch("https://blog.golem.network/rss/"), limit=3)

def fetch_ollama_releases():
    return parse_rss(fetch("https://github.com/ollama/ollama/releases.atom"), limit=3)

def run():
    log("rss_monitor started")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    sections = []

    sources = [
        ("Dev.to Trending", fetch_devto_trending),
        ("Hacker News Top", fetch_hackernews),
        ("r/LocalLLaMA Hot", fetch_reddit_localllama),
        ("Golem Blog", fetch_golem_blog),
        ("Ollama Releases", fetch_ollama_releases),
    ]

    total = 0
    for name, fn in sources:
        items = fn()
        log(f"{name}: {len(items)} items")
        if items:
            section = f"## {name}\n"
            for title, link, meta in items:
                section += f"- **{title}** — {meta}\n  {link}\n"
            sections.append(section)
            total += len(items)

    if sections:
        output = f"# Echo World Context\n_Updated: {now}_\n\n"
        output += "\n".join(sections)
        OUTPUT.parent.mkdir(exist_ok=True)
        OUTPUT.write_text(output)
        log(f"world_context.md updated — {total} items across {len(sections)} sources")

        # Log to event ledger
        try:
            sys.path.insert(0, str(BASE))
            from core.event_ledger import log_event
            log_event("knowledge", "rss_monitor", f"world context updated: {total} items from {len(sections)} sources", score=1.0)
        except Exception:
            pass
    else:
        log("no items fetched — world_context.md not updated")

if __name__ == "__main__":
    run()
