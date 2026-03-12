"""
income_researcher.py — Echo's self-directed income discovery engine

Scrapes relevant sources weekly, extracts income/monetization ideas,
filters for relevance to Echo's actual capabilities, and writes a living
document to memory/income_knowledge.md that Echo reasons about.

Run: python3 -m core.income_researcher
Timer: echo-income-research.timer (weekly, Sunday 4am)
"""

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

BASE_DIR = Path.home() / "Echo"
OUTPUT_MD = BASE_DIR / "memory" / "income_knowledge.md"
CACHE_JSON = BASE_DIR / "memory" / "income_research_cache.json"
LOG_PATH = BASE_DIR / "logs" / "income_researcher.log"

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [income_researcher] %(levelname)s: %(message)s"
)
log = logging.getLogger("income_researcher")

# ── Keywords that signal relevance to Echo's capabilities ──────────────────
RELEVANT_KEYWORDS = [
    "self-host", "selfhost", "inference", "local AI", "local model",
    "ollama", "llm api", "monetize", "passive income", "compute",
    "golem", "render farm", "gpu rental", "api endpoint", "automation",
    "freelance", "AI agent", "workflow", "earning", "revenue",
    "side project", "micro saas", "open source", "developer income",
    "AI tool", "ai startup", "ai service", "sell compute",
]

EXCLUDE_KEYWORDS = [
    "crypto scam", "nft", "dropship", "mlm", "get rich quick",
]

USER_AGENT = "Echo-IncomeResearcher/1.0 (educational; contact via github.com/crow2673/Echo-core)"

# ── Sources ────────────────────────────────────────────────────────────────
SOURCES = [
    {
        "name": "Hacker News — Ask HN / Show HN",
        "url": "https://news.ycombinator.com/rss",
        "type": "rss",
        "notes": "Community surface for new tools, indie projects, earning threads",
    },
    {
        "name": "Dev.to — AI tag",
        "url": "https://dev.to/feed/tag/ai",
        "type": "rss",
        "notes": "Developer monetization stories, AI side projects",
    },
    {
        "name": "Dev.to — Productivity tag",
        "url": "https://dev.to/feed/tag/productivity",
        "type": "rss",
        "notes": "Automation income, tool building stories",
    },
    {
        "name": "Reddit — r/selfhosted",
        "url": "https://www.reddit.com/r/selfhosted.rss",
        "type": "rss",
        "notes": "Self-hosted compute monetization, community use cases",
    },
    {
        "name": "Reddit — r/LocalLLaMA",
        "url": "https://www.reddit.com/r/LocalLLaMA.rss",
        "type": "rss",
        "notes": "Local model deployment, API reselling discussions",
    },
    {
        "name": "Reddit — r/SideProject",
        "url": "https://www.reddit.com/r/SideProject.rss",
        "type": "rss",
        "notes": "Real developers sharing what earns money",
    },
    {
        "name": "Golem Network Blog",
        "url": "https://blog.golem.network/rss/",
        "type": "rss",
        "notes": "Provider tips, earning updates, new task types",
    },
]

# ── Known income mechanisms (baseline, always included) ───────────────────
KNOWN_MECHANISMS = [
    {
        "name": "Golem Network — Compute Provider",
        "description": "Sell GPU/CPU compute to the Golem marketplace. Passive once running.",
        "realistic_ceiling": "~$20-80/month for a single RTX 3060 at current rates",
        "what_it_needs": "yagna running, competitive pricing, patience (new node penalty ~7-14 days)",
        "echo_status": "ACTIVE — node running, 0 tasks completed (new node penalty phase)",
        "effort": "low (passive)",
        "verified": True,
    },
    {
        "name": "Dev.to Content — AI Writing",
        "description": "Publish technical articles. Build audience. Monetize via dev.to badges, sponsorships.",
        "realistic_ceiling": "$5-50/article in badges initially; sponsorship possible at 1k+ followers",
        "what_it_needs": "Consistent publishing, quality, niche authority",
        "echo_status": "ACTIVE — 1 article published, 1 scheduled Tuesday 2026-03-17",
        "effort": "medium (weekly writing)",
        "verified": True,
    },
    {
        "name": "Local LLM API Reselling",
        "description": "Expose Echo's Ollama instance as a pay-per-use API endpoint. Charge for inference.",
        "realistic_ceiling": "$50-300/month depending on model quality and pricing",
        "what_it_needs": "Public endpoint (reverse proxy), auth layer, billing (Stripe), terms of service",
        "echo_status": "NOT STARTED — infrastructure exists, needs auth + billing layer",
        "effort": "high (build once, then passive)",
        "verified": False,
    },
    {
        "name": "Freelance Task Execution",
        "description": "Accept paid tasks (research, writing, summarization, data processing) via a storefront.",
        "realistic_ceiling": "$10-50/task; scalable if automated",
        "what_it_needs": "Storefront (Gumroad, own site), trust signals, intake → auto_act pipeline",
        "echo_status": "NOT STARTED — auto_act pipeline exists but no intake storefront",
        "effort": "medium (storefront setup + task routing)",
        "verified": False,
    },
    {
        "name": "Echo Shell / Setup Wizard Product",
        "description": "Package Echo as a deployable product. Charge builders to spin up their own Echo.",
        "realistic_ceiling": "$50-500/license; recurring if SaaS model",
        "what_it_needs": "Stable core, installer, documentation, pricing page",
        "echo_status": "LONG TERM — core must be proven first",
        "effort": "very high (product build)",
        "verified": False,
    },
    {
        "name": "GPU Rental — Vast.ai / RunPod",
        "description": "Rent RTX 3060 to researchers and developers on GPU rental marketplaces.",
        "realistic_ceiling": "$1.50-3.00/hr * utilization; $30-90/month realistic",
        "what_it_needs": "Account on Vast.ai or RunPod, machine registered, uptime",
        "echo_status": "NOT STARTED — hardware available, account not created",
        "effort": "low (passive once registered)",
        "verified": False,
    },
]


def fetch_rss(url: str, timeout: int = 10) -> list[dict]:
    """Fetch and parse an RSS feed. Returns list of {title, link, summary}."""
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        items = []
        # Handle both RSS 2.0 and Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for item in root.iter("item"):
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            desc = item.findtext("description") or ""
            items.append({"title": title, "link": link, "summary": desc[:400]})
        if not items:
            for entry in root.findall(".//atom:entry", ns):
                title = entry.findtext("atom:title", namespaces=ns) or ""
                link_el = entry.find("atom:link", ns)
                link = link_el.attrib.get("href", "") if link_el is not None else ""
                summary = entry.findtext("atom:summary", namespaces=ns) or ""
                items.append({"title": title, "link": link, "summary": summary[:400]})
        log.info(f"Fetched {len(items)} items from {url}")
        return items
    except (URLError, HTTPError) as e:
        log.warning(f"Could not reach {url}: {e}")
        return []
    except ET.ParseError as e:
        log.warning(f"RSS parse error for {url}: {e}")
        return []


def is_relevant(title: str, summary: str) -> bool:
    """Check if an item is relevant to Echo's income goals."""
    text = (title + " " + summary).lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in text:
            return False
    for kw in RELEVANT_KEYWORDS:
        if kw.lower() in text:
            return True
    return False


def strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text).strip()


def research_all_sources() -> dict:
    """Fetch all sources, filter for relevance, return structured findings."""
    findings = {}
    for source in SOURCES:
        log.info(f"Researching: {source['name']}")
        items = fetch_rss(source["url"])
        relevant = []
        for item in items:
            title = strip_html(item.get("title", ""))
            summary = strip_html(item.get("summary", ""))
            if is_relevant(title, summary):
                relevant.append({
                    "title": title,
                    "link": item.get("link", ""),
                    "summary": summary[:300],
                })
        findings[source["name"]] = {
            "meta": source,
            "total_fetched": len(items),
            "relevant_count": len(relevant),
            "items": relevant[:10],  # cap per source
        }
        time.sleep(1.5)  # be polite
    return findings


def build_markdown(findings: dict, run_time: str) -> str:
    """Build the income_knowledge.md document from findings + known mechanisms."""
    lines = []
    lines.append("# Echo Income Knowledge Base")
    lines.append(f"\n_Last updated: {run_time}_")
    lines.append("\nThis document is generated weekly by `income_researcher.py`.")
    lines.append("Echo reads this file and reasons about which income paths to pursue.")
    lines.append("\n---\n")

    # ── Known mechanisms ──
    lines.append("## Known Income Mechanisms\n")
    lines.append("These are verified or researched paths Echo can pursue:\n")
    for m in KNOWN_MECHANISMS:
        status_icon = "✅" if m["verified"] else "🔲"
        lines.append(f"### {status_icon} {m['name']}")
        lines.append(f"**What it is:** {m['description']}")
        lines.append(f"**Realistic ceiling:** {m['realistic_ceiling']}")
        lines.append(f"**What it needs:** {m['what_it_needs']}")
        lines.append(f"**Echo's current status:** {m['echo_status']}")
        lines.append(f"**Effort level:** {m['effort']}\n")

    # ── Discovered items ──
    lines.append("---\n")
    lines.append("## Discovered This Week\n")
    lines.append("Items scraped from the web that may signal new income opportunities:\n")

    total_discovered = 0
    for source_name, data in findings.items():
        items = data.get("items", [])
        if not items:
            continue
        lines.append(f"### {source_name}")
        lines.append(f"_{data['relevant_count']} relevant of {data['total_fetched']} fetched_\n")
        for item in items:
            title = item.get("title", "").replace("\n", " ")
            link = item.get("link", "")
            summary = item.get("summary", "").replace("\n", " ")
            lines.append(f"- **[{title}]({link})**")
            if summary:
                lines.append(f"  {summary[:200]}")
        lines.append("")
        total_discovered += len(items)

    if total_discovered == 0:
        lines.append("_No new relevant items discovered this week._\n")

    # ── Reasoning prompt for Echo ──
    lines.append("---\n")
    lines.append("## Echo's Standing Questions\n")
    lines.append("When Echo reads this file, she should consider:\n")
    lines.append("1. Which income mechanism is closest to being ready to activate?")
    lines.append("2. What single action this week would move the highest-potential path forward?")
    lines.append("3. Are any discovered items above describing something new I should add to the known mechanisms list?")
    lines.append("4. What is my honest estimate of income earned so far vs. effort invested?")
    lines.append("5. Which path has the best effort-to-income ratio given my current capabilities?\n")

    lines.append("---\n")
    lines.append(f"_Generated by Echo income_researcher.py | {run_time}_\n")

    return "\n".join(lines)


def save_cache(findings: dict, run_time: str):
    """Save raw findings to JSON cache for inspection."""
    cache = {
        "last_run": run_time,
        "findings": {
            name: {
                "total_fetched": data["total_fetched"],
                "relevant_count": data["relevant_count"],
                "items": data["items"],
            }
            for name, data in findings.items()
        }
    }
    CACHE_JSON.write_text(json.dumps(cache, indent=2))
    log.info(f"Cache saved to {CACHE_JSON}")


def run():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    log.info(f"Income research run starting — {run_time}")

    findings = research_all_sources()
    md = build_markdown(findings, run_time)

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(md)
    log.info(f"income_knowledge.md written ({len(md)} chars)")

    save_cache(findings, run_time)

    total = sum(d["relevant_count"] for d in findings.values())
    print(f"[income_researcher] Done. {total} relevant items found. → {OUTPUT_MD}")


if __name__ == "__main__":
    run()
