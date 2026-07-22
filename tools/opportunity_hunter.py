#!/usr/bin/env python3
"""
tools/opportunity_hunter.py — Echo hunts for real paying work on the internet.

Scrapes live sources every hour:
  - Freelancer.com API (open, no key) — Python/automation projects, $25-$2000
  - GitHub bounty issues — cash attached to open source PRs
  - r/forhire + r/hiring on Reddit — direct hire posts

For each opportunity:
  - Scores it (can Echo do this? what's the pay?)
  - Generates a proposal or solution draft
  - Saves to memory/opportunities/ pipeline
  - Notifies Andrew when something good is found

Payment always requires a human account to receive — but Echo does all the work.
Andrew's job: sign up on platform, approve the submission.
"""
import hashlib
import json
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
OPP_DIR = BASE / "memory" / "opportunities"
OPP_DIR.mkdir(parents=True, exist_ok=True)
OPP_PIPELINE = BASE / "memory" / "opportunity_pipeline.json"
LOG = BASE / "logs" / "opportunity_hunter.log"
LOG.parent.mkdir(exist_ok=True)

FREELANCER_API = "https://www.freelancer.com/api"
GITHUB_API = "https://api.github.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# Skills Echo can genuinely deliver on
ECHO_SKILLS = [
    "python", "automation", "script", "scraper", "bot", "api",
    "data", "csv", "excel", "json", "selenium", "playwright",
    "flask", "fastapi", "scheduler", "cron", "email", "telegram",
    "trading", "crypto", "algorithm", "machine learning", "ai",
    "n8n", "zapier", "airtable", "notion", "webhook",
]

# Hard excludes — Echo can't do these
CANT_DO = [
    "mobile app", "ios", "android", "react native", "swift", "kotlin",
    "wordpress plugin", "shopify theme", "video editing", "logo design",
    "translation", "legal", "accounting", "phone", "voice", "call",
    "unity", "unreal", "game dev", "3d model", "photoshop", "illustrator",
]

MIN_BUDGET_USD = 25
MAX_STALENESS_HOURS = 48


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [opportunity] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def load_env():
    env = {}
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()
    return env


def load_pipeline():
    if OPP_PIPELINE.exists():
        try:
            return json.loads(OPP_PIPELINE.read_text())
        except Exception:
            pass
    return {"opportunities": {}, "stats": {"found": 0, "proposed": 0, "submitted": 0, "won": 0}}


def save_pipeline(data):
    tmp = OPP_PIPELINE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(OPP_PIPELINE)


def _get(url, headers=None, timeout=15) -> dict | list | None:
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        log(f"  GET failed {url[:60]}: {e}")
        return None


def _score_opportunity(title: str, description: str, budget_min: float, budget_max: float) -> tuple[int, str]:
    """
    Score an opportunity 0-10.
    Returns (score, reason).
    """
    text = (title + " " + description).lower()

    # Hard excludes
    for cant in CANT_DO:
        if cant in text:
            return 0, f"out of scope: {cant}"

    # Budget gate
    if budget_max < MIN_BUDGET_USD:
        return 0, f"budget too low: ${budget_max}"

    # Skill match scoring
    skill_hits = [s for s in ECHO_SKILLS if s in text]
    if not skill_hits:
        return 2, "no skill match"

    score = min(4 + len(skill_hits), 9)

    # Bonus for high budget
    if budget_min >= 200:
        score = min(score + 1, 10)
    if budget_min >= 500:
        score = min(score + 1, 10)

    reason = f"skills: {skill_hits[:4]}, budget ${budget_min}-${budget_max}"
    return score, reason


def _call_ollama(prompt: str, system: str, timeout: int = 90) -> str:
    payload = json.dumps({
        "model": "qwen2.5:7b",
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 600, "temperature": 0.3},
    }).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()).get("response", "").strip()
    except Exception as e:
        log(f"  Ollama error: {e}")
        return ""


def _generate_proposal(title: str, description: str, budget: str, platform: str) -> str:
    system = (
        "You are Echo — a Python automation expert. Write a short, winning freelance proposal.\n"
        "Rules: under 150 words. Specific — reference their exact problem. "
        "Lead with what you'll deliver, not who you are. End with timeline and price."
    )
    prompt = (
        f"Platform: {platform}\n"
        f"Project: {title}\n"
        f"Description: {description[:500]}\n"
        f"Budget: {budget}\n\n"
        "Write a proposal that will win this project."
    )
    return _call_ollama(prompt, system, timeout=60)


def _opp_id(source: str, external_id: str) -> str:
    return hashlib.md5(f"{source}:{external_id}".encode()).hexdigest()[:12]


# ── Source 1: Freelancer.com ──────────────────────────────────────────────────

def _scan_freelancer() -> list[dict]:
    """Scan Freelancer.com for Python/automation projects."""
    found = []

    # Multiple search queries to cover Echo's skill set
    queries = [
        "python automation script",
        "python bot scraper",
        "python data automation",
        "automation workflow api",
    ]

    seen_ids = set()
    for query in queries:
        enc = urllib.parse.quote(query)
        url = (
            f"{FREELANCER_API}/projects/0.1/projects/active/"
            f"?limit=10&full_description=true&query={enc}"
            f"&min_avg_price={MIN_BUDGET_USD}&max_avg_price=5000"
        )
        data = _get(url)
        if not data:
            continue

        projects = data.get("result", {}).get("projects", [])
        for p in projects:
            pid = str(p.get("id", ""))
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            budget = p.get("budget") or {}
            b_min = float(budget.get("minimum") or 0)
            b_max = float(budget.get("maximum") or 0)
            title = p.get("title", "")
            desc = p.get("description") or ""
            seo = p.get("seo_url", "")

            score, reason = _score_opportunity(title, desc, b_min, b_max)
            if score < 5:
                continue

            found.append({
                "id": _opp_id("freelancer", pid),
                "source": "freelancer",
                "external_id": pid,
                "title": title,
                "description": desc[:600],
                "budget_min": b_min,
                "budget_max": b_max,
                "budget_str": f"${b_min:.0f}-${b_max:.0f}",
                "url": f"https://www.freelancer.com/projects/{seo}",
                "score": score,
                "score_reason": reason,
                "found_at": datetime.now().isoformat(),
                "status": "new",
            })

        time.sleep(1)  # be polite

    log(f"  freelancer: {len(found)} scoreable projects")
    return found


# ── Source 2: GitHub Bounties ─────────────────────────────────────────────────

def _scan_github_bounties() -> list[dict]:
    """Find GitHub issues with cash bounties on them."""
    found = []
    env = load_env()
    headers = {}
    if env.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {env['GITHUB_TOKEN']}"

    # Search for bounty-labeled Python issues
    queries = [
        "label:bounty+language:python+state:open",
        "label:\"good+first+issue\"+label:bounty+state:open",
        '"$"+bounty+python+automation+state:open',
    ]

    seen = set()
    for q in queries:
        url = f"{GITHUB_API}/search/issues?q={urllib.parse.quote(q)}&sort=created&per_page=10"
        data = _get(url, headers=headers)
        if not data:
            continue

        for issue in data.get("items", []):
            iid = str(issue.get("id", ""))
            if iid in seen:
                continue
            seen.add(iid)

            title = issue.get("title", "")
            body = issue.get("body") or ""
            html_url = issue.get("html_url", "")
            repo = issue.get("repository_url", "").replace("https://api.github.com/repos/", "")

            # Try to extract dollar amount from title/body
            amounts = re.findall(r'\$\s*(\d[\d,]*)', title + " " + body[:500])
            if not amounts:
                continue
            try:
                b_min = float(amounts[0].replace(",", ""))
            except Exception:
                b_min = 50

            score, reason = _score_opportunity(title, body, b_min, b_min)
            if score < 4:
                continue

            found.append({
                "id": _opp_id("github", iid),
                "source": "github_bounty",
                "external_id": iid,
                "title": title,
                "description": body[:600],
                "budget_min": b_min,
                "budget_max": b_min,
                "budget_str": f"${b_min:.0f}",
                "url": html_url,
                "repo": repo,
                "score": score,
                "score_reason": reason,
                "found_at": datetime.now().isoformat(),
                "status": "new",
            })

        time.sleep(0.5)

    log(f"  github bounties: {len(found)} found")
    return found


# ── Source 3: Reddit forhire ──────────────────────────────────────────────────

def _scan_reddit_forhire() -> list[dict]:
    """Scan r/forhire and r/hiring for Python work."""
    found = []
    headers = {"User-Agent": "Echo-OppHunter/1.0"}

    for sub in ["forhire", "hiring"]:
        url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
        except Exception:
            continue

        posts = data.get("data", {}).get("children", [])
        for post in posts:
            p = post.get("data", {})
            title = p.get("title", "")
            body = p.get("selftext", "")
            post_id = p.get("id", "")

            # Only [HIRING] posts
            if "[hiring]" not in title.lower() and "hiring" not in title.lower()[:20]:
                continue

            # Extract budget
            amounts = re.findall(r'\$\s*(\d[\d,]*)', title + " " + body[:300])
            b_min = float(amounts[0].replace(",", "")) if amounts else 50

            score, reason = _score_opportunity(title, body, b_min, b_min * 2)
            if score < 5:
                continue

            found.append({
                "id": _opp_id("reddit", post_id),
                "source": "reddit_forhire",
                "external_id": post_id,
                "title": title,
                "description": body[:600],
                "budget_min": b_min,
                "budget_max": b_min * 2,
                "budget_str": f"~${b_min:.0f}",
                "url": f"https://reddit.com{p.get('permalink', '')}",
                "score": score,
                "score_reason": reason,
                "found_at": datetime.now().isoformat(),
                "status": "new",
            })

        time.sleep(2)

    log(f"  reddit forhire: {len(found)} matching")
    return found


# ── Pipeline management ───────────────────────────────────────────────────────

def _process_opportunity(opp: dict, pipeline: dict) -> bool:
    """Generate proposal for a new opportunity. Returns True if proposal was made."""
    opp_id = opp["id"]
    if opp_id in pipeline["opportunities"]:
        return False  # already seen

    log(f"  processing: [{opp['score']}/10] {opp['title'][:60]} | {opp['budget_str']}")

    proposal = _generate_proposal(
        opp["title"],
        opp["description"],
        opp["budget_str"],
        opp["source"],
    )

    opp["proposal"] = proposal
    opp["status"] = "proposed" if proposal else "new"

    # Save individual opportunity file
    opp_file = OPP_DIR / f"{opp_id}.json"
    opp_file.write_text(json.dumps(opp, indent=2))

    pipeline["opportunities"][opp_id] = {
        "title": opp["title"][:80],
        "source": opp["source"],
        "budget": opp["budget_str"],
        "score": opp["score"],
        "url": opp["url"],
        "status": opp["status"],
        "found_at": opp["found_at"],
    }
    pipeline["stats"]["found"] = pipeline["stats"].get("found", 0) + 1
    if proposal:
        pipeline["stats"]["proposed"] = pipeline["stats"].get("proposed", 0) + 1

    return bool(proposal)


def _notify_best(new_opps: list[dict]):
    """Notify Andrew about the best new opportunities found."""
    if not new_opps:
        return
    best = sorted(new_opps, key=lambda o: (o["score"], o["budget_min"]), reverse=True)[:3]
    try:
        from core.notifier import notify
        lines = []
        for o in best:
            lines.append(f"[{o['score']}/10] {o['budget_str']} — {o['title'][:60]}")
            lines.append(f"  {o['url']}")
        notify(
            f"Echo found {len(new_opps)} paying opportunities",
            "\n".join(lines),
            urgent=False,
        )
    except Exception:
        pass


def run() -> dict:
    log("starting opportunity hunt")
    pipeline = load_pipeline()

    all_found = []

    # Scan all sources
    all_found += _scan_freelancer()
    all_found += _scan_github_bounties()
    all_found += _scan_reddit_forhire()

    log(f"total found across all sources: {len(all_found)}")

    # Process new ones — generate proposals
    new_with_proposals = []
    for opp in all_found:
        if _process_opportunity(opp, pipeline):
            new_with_proposals.append(opp)

    save_pipeline(pipeline)

    if new_with_proposals:
        _notify_best(new_with_proposals)

    total_in_pipeline = len(pipeline["opportunities"])
    stats = pipeline["stats"]

    log(f"done — {len(new_with_proposals)} new proposals | pipeline: {total_in_pipeline} total | {stats}")

    return {
        "new_found": len(all_found),
        "new_proposals": len(new_with_proposals),
        "pipeline_total": total_in_pipeline,
        "stats": stats,
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, default=str))
