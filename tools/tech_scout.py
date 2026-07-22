#!/usr/bin/env python3
"""
tools/tech_scout.py — Echo's technology discovery engine.

Searches PyPI and GitHub trending for libraries relevant to Echo's known gaps.
Scores candidates, then feeds top matches to the assimilator.
Runs weekly via echo-tech-scout.timer.

Echo reads what's new in the world and decides what to learn.
"""
import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

LOG = BASE / "logs/tech_scout.log"
GAPS_FILE = BASE / "memory/known_gaps.md"
SCOUT_LOG = BASE / "memory/tech_scout_history.json"

# Keywords derived from Echo's purpose — what to search for
SEARCH_TERMS = [
    "automation python",
    "trading strategy python",
    "web scraping python",
    "ai agent python",
    "fiverr api",
    "task scheduler python",
    "nlp text classification",
    "sentiment analysis trading",
    "browser automation",
    "data pipeline python",
]

# Libraries already in Echo or known to be irrelevant
SKIP_LIST = {
    "requests", "beautifulsoup4", "selenium", "playwright", "anthropic",
    "openai", "langchain", "pandas", "numpy", "sqlite3", "pathlib",
    "freqtrade", "alpaca-trade-api", "praw", "schedule", "psutil",
}

MAX_CANDIDATES_PER_RUN = 5
MIN_RELEVANCE_SCORE = 6


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[tech_scout] {msg}", flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def _load_history() -> dict:
    if SCOUT_LOG.exists():
        try:
            return json.loads(SCOUT_LOG.read_text())
        except Exception:
            pass
    return {"seen": [], "runs": []}


def _save_history(data: dict):
    tmp = SCOUT_LOG.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(SCOUT_LOG)


def search_pypi(query: str, max_results: int = 10) -> list[dict]:
    """Search PyPI for packages matching a query."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://pypi.org/search/?q={encoded}&o=-zscore&c=Programming+Language+%3A%3A+Python"
        req = urllib.request.Request(url, headers={"User-Agent": "Echo-TechScout/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="ignore")

        # Parse package names from PyPI search results HTML
        packages = []
        import re
        # PyPI search result pattern
        matches = re.findall(
            r'<span class="package-snippet__name">\s*([^<]+)\s*</span>.*?'
            r'<p class="package-snippet__description">\s*([^<]*)\s*</p>',
            html, re.DOTALL
        )
        for name, desc in matches[:max_results]:
            name = name.strip()
            desc = desc.strip()
            if name and name.lower() not in SKIP_LIST:
                packages.append({"name": name, "description": desc})

        return packages
    except Exception as e:
        log(f"PyPI search failed for '{query}': {e}")
        return []


def score_candidate(package: dict, gaps_text: str) -> int:
    """Quick keyword-based relevance score before LLM evaluation."""
    text = (package.get("name", "") + " " + package.get("description", "")).lower()
    score = 0

    # Echo's core needs
    keywords = {
        "trading": 3, "automation": 3, "ai": 2, "agent": 2,
        "scraping": 2, "scheduler": 2, "workflow": 2,
        "income": 2, "freelance": 2, "fiverr": 3,
        "async": 1, "monitor": 1, "alert": 1,
        "crypto": 2, "sentiment": 2, "nlp": 1,
    }
    for kw, weight in keywords.items():
        if kw in text:
            score += weight

    # Penalize if description is empty or generic
    if not package.get("description"):
        score -= 2

    return min(score, 10)


def run():
    log("tech scout starting")
    history = _load_history()
    seen = set(history.get("seen", []))

    candidates = []

    for term in SEARCH_TERMS:
        results = search_pypi(term, max_results=8)
        log(f"'{term}': {len(results)} results")
        for pkg in results:
            name = pkg["name"]
            if name in seen or name.lower() in SKIP_LIST:
                continue
            seen.add(name)
            score = score_candidate(pkg, "")
            if score >= 3:  # pre-filter before LLM
                candidates.append({**pkg, "quick_score": score, "search_term": term})

    # Sort by quick score, take top N for LLM evaluation
    candidates.sort(key=lambda x: x["quick_score"], reverse=True)
    top = candidates[:MAX_CANDIDATES_PER_RUN]
    log(f"Found {len(candidates)} candidates, evaluating top {len(top)}")

    if not top:
        log("No new candidates found this run")
        history["seen"] = list(seen)
        history["runs"].append({"at": datetime.now().isoformat(), "found": 0})
        _save_history(history)
        return

    # Feed top candidates to assimilator
    from core.assimilator import assimilate
    integrated = []

    for pkg in top:
        log(f"Evaluating: {pkg['name']} (score={pkg['quick_score']}) — {pkg['description'][:50]}")
        try:
            result = assimilate(pkg["name"])
            if result.get("status") == "integrated":
                integrated.append(pkg["name"])
                log(f"INTEGRATED: {pkg['name']}")
            else:
                log(f"Skipped: {pkg['name']} ({result.get('status')})")
        except Exception as e:
            log(f"Assimilation failed for {pkg['name']}: {e}")

    history["seen"] = list(seen)
    history["runs"].append({
        "at": datetime.now().isoformat(),
        "candidates_found": len(candidates),
        "evaluated": len(top),
        "integrated": integrated,
    })
    _save_history(history)

    log(f"Scout complete — {len(integrated)} new skills integrated: {integrated}")

    # Promote newly discovered tools into persistent goals for Echo to explore
    try:
        from core.persistent_goals import add_goal
        for pkg in top:
            if pkg["name"] not in integrated:
                goal_id = f"explore_{pkg['name'].replace('-','_')[:30]}"
                add_goal(
                    goal_id=goal_id,
                    description=(
                        f"Explore external tool '{pkg['name']}': {pkg['description'][:100]}. "
                        f"Investigate if it can improve Echo's capabilities or open new income paths. "
                        f"If useful, integrate it."
                    ),
                    source="tech_scout",
                )
    except Exception as _e:
        log(f"Goal promotion failed: {_e}")

    if integrated:
        try:
            from core.notifier import notify as notify_telegram
            notify_telegram(
                "Echo Tech Scout",
                f"Scout run complete.\n\n"
                f"Evaluated: {len(top)} libraries\n"
                f"Integrated: {len(integrated)}\n"
                f"New skills: {', '.join(integrated)}"
            )
        except Exception:
            pass


if __name__ == "__main__":
    run()
