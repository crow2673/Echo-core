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


def build_signals_section(relevant_items):
    lines = [
        "## Market Signals This Week",
        f"_{len(relevant_items)} relevant items found across {len(SOURCES)} sources_",
        "",
    ]
    for item in relevant_items[:10]:
        lines.append(f"- **{item['title'][:80]}**")
        if item.get("link"):
            lines.append(f"  {item['link']}")
        lines.append("")
    return "\n".join(lines)


def update_markdown(relevant_items):
    """Update only the Market Signals section in income_knowledge.md. Preserve everything else."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    signals = build_signals_section(relevant_items)

    if OUTPUT.exists():
        existing = OUTPUT.read_text()
        # Update timestamp
        import re
        existing = re.sub(r"_Last updated:.*?_", f"_Last updated: {now}_", existing, count=1)
        # Replace Market Signals section only
        if "## Market Signals This Week" in existing:
            # Find start of section and end (next ## heading or EOF)
            start = existing.index("## Market Signals This Week")
            rest = existing[start:]
            next_section = rest.find("\n## ", 1)
            if next_section != -1:
                after = rest[next_section:]
            else:
                after = ""
            existing = existing[:start] + signals + ("\n\n" if after else "") + after.lstrip("\n")
        else:
            existing = existing.rstrip() + "\n\n" + signals
        return existing
    else:
        # File doesn't exist — write a minimal bootstrap
        return f"# Echo Income Knowledge Base\n_Last updated: {now}_\n\n{signals}"


def run():
    logging.info(f"Income research run starting — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    all_items = []
    for name, url in SOURCES:
        items = fetch_rss(name, url)
        all_items.extend(items)

    relevant = [i for i in all_items if is_relevant(i)]
    logging.info(f"{len(relevant)} relevant items from {len(all_items)} total")

    md = update_markdown(relevant)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = OUTPUT.with_suffix(".tmp")
    tmp_out.write_text(md)
    tmp_out.rename(OUTPUT)
    logging.info(f"income_knowledge.md updated ({len(md)} chars)")

    cache_data = json.dumps({
        "updated_at": datetime.now().isoformat(),
        "item_count": len(relevant),
        "sources": len(SOURCES),
    }, indent=2)
    tmp_cache = CACHE.with_suffix(".tmp")
    tmp_cache.write_text(cache_data)
    tmp_cache.rename(CACHE)
    logging.info(f"Cache saved to {CACHE}")
    print(f"[income_researcher] Done. {len(relevant)} relevant items found. → {OUTPUT}")

    # Promote high-signal discoveries into persistent goals Echo will actively pursue
    try:
        from core.persistent_goals import add_goal
        from core.assimilator import run as assimilate
        for item in relevant[:5]:
            title = item.get("title", "")
            url = item.get("url", item.get("link", ""))
            source = item.get("source", "")
            # Create a goal to investigate and act on each strong signal
            goal_id = f"signal_{hash(url) % 100000}"
            add_goal(
                goal_id=goal_id,
                description=(
                    f"Investigate and act on external signal: '{title[:80]}' "
                    f"(from {source}). Search for actionable income opportunity. "
                    f"If a useful library or tool is mentioned, assimilate it."
                ),
                source="income_researcher",
            )
        # Also try to assimilate any library/tool mentioned in relevant items
        for item in relevant:
            body = item.get("summary", item.get("description", ""))
            title = item.get("title", "")
            text = (title + " " + body).lower()
            # Look for Python package mentions
            import re as _re
            packages = _re.findall(r'\b([a-z][a-z0-9_-]{2,}(?:\.py)?)\b', text)
            for pkg in set(packages[:3]):
                if len(pkg) > 3 and pkg not in ("this", "that", "with", "from", "http", "https", "the", "and"):
                    try:
                        assimilate(pkg)
                    except Exception:
                        pass
    except Exception as _e:
        logging.warning(f"goal/assimilation promotion failed: {_e}")


if __name__ == "__main__":
    run()
