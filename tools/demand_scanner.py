#!/usr/bin/env python3
"""
demand_scanner.py — Echo's Reddit lead scanner for Fiverr gig income
Runs hourly via echo-demand-scanner.timer.

Scans subreddits for people who need Python automation / AI tools.
Scores posts 1-10. Saves high-value leads to demand_leads.json.
Alerts via Telegram for score >= 8. Logs to Notion NOTION_DB_LEADS.
"""
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LEADS_FILE = BASE / "memory/demand_leads.json"
SCAN_STATE_FILE = BASE / "memory/demand_state.json"
LOG_FILE = BASE / "logs/demand_scanner.log"

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s %(message)s",
)

USER_AGENT = "echo-demand-scanner/1.0 (autonomous income agent; contact: echo-andrew)"
SUBREDDIT_COOLDOWN = 3300  # 55 min between scans of same subreddit
SCORE_THRESHOLD_ALERT = 8   # instant Telegram alert
SCORE_THRESHOLD_DIGEST = 6  # include in digest
SCORE_THRESHOLD_SAVE = 5    # save to leads file

SUBREDDITS = [
    "r/smallbusiness", "r/Entrepreneur", "r/startups",
    "r/SideProject", "r/learnpython", "r/Python",
    "r/automation", "r/nocode", "r/zapier",
    "r/freelance", "r/forhire", "r/hiring",
]

HIGH_VALUE_KEYWORDS = [
    "automate", "automation", "script", "scraper", "bot",
    "python", "api", "integrate", "workflow", "save time",
    "data entry", "spreadsheet", "airtable", "notion api",
    "fiverr", "hire", "looking for", "need someone",
]
MEDIUM_KEYWORDS = [
    "tool", "software", "app", "dashboard", "report",
    "email", "schedule", "repeat", "manual", "tedious",
]
BUYER_SIGNALS = [
    "hire", "pay", "budget", "quote", "how much", "looking for",
    "need help", "need someone", "can someone", "anyone able",
    "willing to pay", "freelancer", "developer", "build for me",
]
SELLER_SIGNALS = [
    "i offer", "i build", "i make", "my service", "check out my",
    "fiverr.com", "upwork.com", "available for hire", "dm me",
]
EXCLUDE_KEYWORDS = [
    "hiring manager", "job posting", "full time", "full-time",
    "salary", "benefits", "remote work", "years experience",
]

ENV = {}


def load_env():
    global ENV
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                ENV[k.strip()] = v.strip()


def log(msg):
    print(msg, flush=True)
    logging.info(msg)


def load_leads():
    if LEADS_FILE.exists():
        try:
            return json.loads(LEADS_FILE.read_text())
        except Exception:
            pass
    return []


def save_leads(leads):
    LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEADS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(leads, indent=2, default=str))
    tmp.rename(LEADS_FILE)


def load_state():
    if SCAN_STATE_FILE.exists():
        try:
            return json.loads(SCAN_STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state):
    SCAN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SCAN_STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str))
    tmp.rename(SCAN_STATE_FILE)


def subreddit_needs_scan(subreddit, state):
    key = f"last_scan_{subreddit}"
    last = state.get(key)
    if not last:
        return True
    try:
        elapsed = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
        return elapsed >= SUBREDDIT_COOLDOWN
    except Exception:
        return True


def fetch_new_posts(subreddit, limit=25):
    """Fetch new posts from a subreddit using public JSON API."""
    name = subreddit.replace("r/", "")
    url = f"https://www.reddit.com/r/{name}/new.json?limit={limit}&sort=new"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        posts = data.get("data", {}).get("children", [])
        return [p["data"] for p in posts]
    except urllib.error.HTTPError as e:
        log(f"  [{subreddit}] HTTP {e.code}: skipping")
        return []
    except Exception as e:
        log(f"  [{subreddit}] fetch error: {e}")
        return []


def score_post(post):
    """Score a Reddit post for Fiverr lead relevance (1-10)."""
    title = post.get("title", "").lower()
    body = post.get("selftext", "").lower()
    subreddit = post.get("subreddit", "").lower()
    text = title + " " + body

    # Disqualify
    if any(kw in text for kw in EXCLUDE_KEYWORDS):
        return 0
    if post.get("selftext") in ("[removed]", "[deleted]"):
        return 0

    seller_hit = any(kw in text for kw in SELLER_SIGNALS)
    if seller_hit:
        return 0  # they're selling, not buying

    score = 1
    buyer_hit = any(kw in text for kw in BUYER_SIGNALS)
    if buyer_hit:
        score += 3

    hv_matches = [kw for kw in HIGH_VALUE_KEYWORDS if kw in text]
    hv_check = len(hv_matches)
    score += min(hv_check * 2, 4)

    med_matches = [kw for kw in MEDIUM_KEYWORDS if kw in text]
    score += min(len(med_matches), 2)

    # High-intent subreddits
    if subreddit in ("forhire", "hiring", "learnpython"):
        score += 1

    return min(score, 10)


def extract_lead(post, score, subreddit):
    """Build a lead dict from a Reddit post."""
    return {
        "post_id": post.get("id", "unknown"),
        "title": post.get("title", "")[:200],
        "subreddit": subreddit,
        "url": f"https://reddit.com{post.get('permalink', '')}",
        "body": post.get("selftext", "")[:500],
        "score": score,
        "found_at": datetime.fromtimestamp(post.get("created_utc", 0)).isoformat(),
        "alerted": False,
        "status": "new",
    }


def draft_outreach(lead):
    """Generate a brief outreach DM draft for the lead."""
    title = lead["title"][:60]
    return (
        f"Hey, saw your post about '{title}'. "
        f"I build custom AI automation tools and Python scripts — "
        f"sounds like exactly what I do on Fiverr. Happy to scope it out for free."
    )


def drop_to_notion(lead):
    """Write strong lead to Notion NOTION_DB_LEADS database."""
    token = ENV.get("NOTION_TOKEN") or os.environ.get("NOTION_TOKEN", "")
    db_id = ENV.get("NOTION_DB_LEADS") or os.environ.get("NOTION_DB_LEADS", "")
    if not token or not db_id:
        log("  [notion] NOTION_DB_LEADS not configured, skipping")
        return
    payload = json.dumps({
        "parent": {"database_id": db_id},
        "properties": {
            "Lead": {"title": [{"text": {"content": lead["title"][:100]}}]},
            "Score": {"number": lead["score"]},
            "Status": {"select": {"name": "New"}},
            "Subreddit": {"rich_text": [{"text": {"content": lead["subreddit"]}}]},
            "Summary": {"rich_text": [{"text": {"content": lead.get("outreach_draft", "")[:300]}}]},
            "URL": {"url": lead["url"]},
            "Found At": {"date": {"start": lead["found_at"]}},
        },
    }).encode()
    req = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        log(f"  [notion] lead logged: {lead['title'][:50]}")
    except Exception as e:
        log(f"  [notion] drop failed: {e}")


def run():
    load_env()
    log(f"[demand_scanner] starting at {datetime.now().strftime('%H:%M:%S')}")

    state = load_state()
    all_leads = load_leads()
    existing_ids = {l["post_id"] for l in all_leads}

    new_leads = []
    alerts_fired = 0
    digest_leads = []

    for subreddit in SUBREDDITS:
        if not subreddit_needs_scan(subreddit, state):
            log(f"  [{subreddit}] on cooldown, skipping")
            continue

        log(f"  [{subreddit}] scanning...")
        posts = fetch_new_posts(subreddit)
        log(f"  [{subreddit}] {len(posts)} posts fetched")

        state[f"last_scan_{subreddit}"] = datetime.now().isoformat()

        for post in posts:
            post_id = post.get("id", "")
            if post_id in existing_ids:
                continue

            score = score_post(post)
            if score < SCORE_THRESHOLD_SAVE:
                continue

            lead = extract_lead(post, score, subreddit)
            lead["outreach_draft"] = draft_outreach(lead)
            new_leads.append(lead)
            existing_ids.add(post_id)
            log(f"  [{subreddit}] LEAD score={score} — {lead['title'][:60]}")

            if score >= SCORE_THRESHOLD_ALERT:
                try:
                    from core.notifier import notify
                    notify(
                        "Fiverr Lead",
                        f"Score {score}/10 in {subreddit}: {lead['title'][:80]}",
                        urgent=True,
                    )
                    lead["alerted"] = True
                    alerts_fired += 1
                except Exception:
                    pass
                drop_to_notion(lead)

            elif score >= SCORE_THRESHOLD_DIGEST:
                digest_leads.append(lead)

    if digest_leads:
        try:
            from core.notifier import notify
            lines = [f"• score={l['score']} [{l['subreddit']}]: {l['title'][:60]}" for l in digest_leads[:5]]
            extra = f"...and {len(digest_leads) - 5} more" if len(digest_leads) > 5 else ""
            msg = "\n".join(lines) + ("\n" + extra if extra else "")
            notify("Lead Digest", msg, urgent=False)
        except Exception:
            pass

    all_leads = new_leads + [l for l in all_leads if l["post_id"] not in {n["post_id"] for n in new_leads}]
    all_leads.sort(key=lambda l: l.get("score", 0), reverse=True)

    save_leads(all_leads)
    save_state(state)

    log(
        f"[demand_scanner] done — {len(new_leads)} new leads, "
        f"{alerts_fired} instant alerts, "
        f"{len(digest_leads)} in digest, "
        f"{len(all_leads)} total in queue"
    )


if __name__ == "__main__":
    run()
