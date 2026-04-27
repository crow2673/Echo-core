#!/usr/bin/env python3
"""
Income researcher — fetches RSS/web signals and writes memory/income_knowledge.md.
Runs weekly (Sunday 4am). Reads HN, dev.to, Reddit for demand signals.
"""
import json
import logging
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

BASE = Path.home() / "Echo"
OUTPUT = BASE / "memory/income_knowledge.md"
CACHE = BASE / "memory/income_research_cache.json"
LOG = BASE / "logs/income_researcher.log"

logging.basicConfig(
    filename=str(LOG),
    level=logging.INFO,
    format="%(asctime)s [income_researcher] %(levelname)s: %(message)s",
)

SOURCES = [
    ("Hacker News — Ask HN / Show HN", "https://news.ycombinator.com/rss"),
    ("Dev.to — AI tag", "https://dev.to/feed/tag/ai"),
    ("Dev.to — Productivity tag", "https://dev.to/feed/tag/productivity"),
    ("Reddit — r/selfhosted", "https://www.reddit.com/r/selfhosted.rss"),
    ("Reddit — r/LocalLLaMA", "https://www.reddit.com/r/LocalLLaMA.rss"),
    ("Reddit — r/SideProject", "https://www.reddit.com/r/SideProject.rss"),
    ("Golem Network Blog", "https://blog.golem.network/rss/"),
]

KEYWORDS = [
    "automation", "local llm", "ollama", "self-hosted", "ai agent",
    "passive income", "fiverr", "freelance", "python script", "workflow",
    "side project", "build in public", "devto", "content strategy",
    "autonomous", "trading bot", "alpaca", "crypto", "income stream",
]


def fetch_rss(name, url, max_items=30):
    logging.info(f"Researching: {name}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EchoResearcher/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        root = ET.fromstring(data)
        items = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()[:200]
            items.append({"title": title, "link": link, "desc": desc})
            if len(items) >= max_items:
                break
        logging.info(f"Fetched {len(items)} items from {url}")
        return items
    except Exception as e:
        logging.warning(f"Failed to fetch {name}: {e}")
        return []


def is_relevant(item):
    text = (item["title"] + " " + item["desc"]).lower()
    return any(kw in text for kw in KEYWORDS)


def build_markdown(relevant_items):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Echo Income Knowledge Base",
        f"_Last updated: {now}_",
        "",
        "## Active Income Streams",
        "",
        "### L1 — Crypto 24/7 (BTC/SOL)",
        "**Echo's current status:** ACTIVE — 67% win rate, +$324 realized | paper trading",
        "",
        "### L2 — Momentum Stocks",
        "**Echo's current status:** ACTIVE — 60% win rate, +$433 realized | paper trading",
        "",
        "### L3 — Trend Stocks",
        "**Echo's current status:** ACTIVE — 25% win rate, -$1,011 realized | stop fix in progress",
        "",
        "### L4 — Income/Index",
        "**Echo's current status:** ACTIVE — 67% win rate, +$652 realized | paper trading",
        "",
        "### Fiverr — AI Automation Builder",
        "**Echo's current status:** ACTIVE — gig live at andrewelliot476 | local Python automation",
        "",
        "### Dev.to Content",
        "**Echo's current status:** ACTIVE — 1 articles published, 1 scheduled Tuesday 2026-03-17",
        "",
        "### Golem Compute",
        "**Echo's current status:** CLOSED — investigation ended 2026-04-24, market demand problem not connectivity",
        "",
        "## Market Signals This Week",
        f"_{len(relevant_items)} relevant items found across {len(SOURCES)} sources_",
        "",
    ]
    for item in relevant_items[:40]:
        lines.append(f"- **{item['title'][:80]}**")
        if item.get("link"):
            lines.append(f"  {item['link']}")
        if item.get("desc"):
            lines.append(f"  _{item['desc'][:120]}_")
        lines.append("")

    lines += [
        "## Key Decisions",
        "- May 15, 2026: Real capital decision — $1,000 into L1 Crypto only (no PDT rule)",
        "- L3 stop loss fix required before real capital deployment",
        "- Reddit outreach blocked pending OAuth write scope",
        "",
        "## Next Actions",
        "- Fix L3 stop loss logic (trade_brain.py — restore from backup)",
        "- Register Reddit app for write scope to enable outreach",
        "- Review L1 paper performance through May 15",
    ]
    return "\n".join(lines)


def run():
    logging.info(f"Income research run starting — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    all_items = []
    for name, url in SOURCES:
        items = fetch_rss(name, url)
        all_items.extend(items)

    relevant = [i for i in all_items if is_relevant(i)]
    logging.info(f"{len(relevant)} relevant items from {len(all_items)} total")

    md = build_markdown(relevant)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(md)
    logging.info(f"income_knowledge.md written ({len(md)} chars)")

    CACHE.write_text(json.dumps({
        "updated_at": datetime.now().isoformat(),
        "item_count": len(relevant),
        "sources": len(SOURCES),
    }, indent=2))
    logging.info(f"Cache saved to {CACHE}")
    print(f"[income_researcher] Done. {len(relevant)} relevant items found. → {OUTPUT}")


if __name__ == "__main__":
    run()
