#!/usr/bin/env python3
"""
core/reddit_outreach.py — Reddit DM sender for Fiverr lead outreach

Sends outreach DMs to Reddit users who posted requests matching Echo's
Fiverr gig. Requires Reddit credentials (OAuth2) in golem.env.

Setup:
  1. Go to https://www.reddit.com/prefs/apps
  2. Create app → script type → redirect: http://localhost:8080
  3. Add to golem.env:
       REDDIT_CLIENT_ID=your_client_id
       REDDIT_CLIENT_SECRET=your_client_secret
       REDDIT_USERNAME=your_reddit_username
       REDDIT_PASSWORD=your_reddit_password
       REDDIT_USER_AGENT=Echo:FiverrOutreach:v1.0 (by u/your_username)
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LOG = BASE / "logs/reddit_outreach.log"
LEADS_FILE = BASE / "memory/demand_leads.json"
SENT_FILE = BASE / "memory/reddit_dms_sent.json"
MAX_DMS_PER_DAY = 5
SCORE_THRESHOLD = 7


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[outreach] {msg}", flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def _get_env():
    env = {}
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def is_configured():
    env = _get_env()
    return all(env.get(k) for k in ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD"])


def _get_reddit():
    """Return authenticated praw.Reddit instance."""
    try:
        import praw
    except ImportError:
        raise RuntimeError("praw not installed: pip install praw --user --break-system-packages")
    env = _get_env()
    return praw.Reddit(
        client_id=env["REDDIT_CLIENT_ID"],
        client_secret=env["REDDIT_CLIENT_SECRET"],
        username=env["REDDIT_USERNAME"],
        password=env["REDDIT_PASSWORD"],
        user_agent=env.get("REDDIT_USER_AGENT", "Echo:FiverrOutreach:v1.0"),
    )


def _load_sent():
    if SENT_FILE.exists():
        try:
            return json.loads(SENT_FILE.read_text())
        except Exception:
            pass
    return []


def _save_sent(sent):
    tmp = SENT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sent, indent=2, default=str))
    tmp.rename(SENT_FILE)


def _already_sent(username, sent):
    return any(s.get("username") == username for s in sent)


def _dms_today(sent):
    cutoff = (datetime.now() - timedelta(days=1)).isoformat()
    return sum(1 for s in sent if s.get("sent_at", "") >= cutoff)


def send_dm(username: str, subject: str, body: str) -> bool:
    """Send a Reddit DM. Returns True on success."""
    if not is_configured():
        log("Reddit credentials not configured — add REDDIT_CLIENT_ID etc to golem.env")
        return False

    sent = _load_sent()
    if _already_sent(username, sent):
        log(f"Already DMed u/{username} — skipping")
        return False

    daily = _dms_today(sent)
    if daily >= MAX_DMS_PER_DAY:
        log(f"Daily DM limit reached ({MAX_DMS_PER_DAY}/day)")
        return False

    try:
        reddit = _get_reddit()
        reddit.redditor(username).message(subject=subject, message=body)
        sent.append({"username": username, "sent_at": datetime.now().isoformat(), "subject": subject})
        _save_sent(sent)
        log(f"DM sent to u/{username}")
        return True
    except Exception as e:
        log(f"DM failed to u/{username}: {e}")
        return False


def send_dm_to_lead(lead: dict) -> bool:
    """Send outreach DM to a lead from demand_scanner."""
    username = lead.get("author", "")
    if not username or username in ("", "[deleted]", "AutoModerator"):
        log(f"Skipping lead with invalid author: '{username}'")
        return False
    draft = lead.get("outreach_draft", "")
    if not draft:
        log(f"No outreach draft for lead: {lead.get('title', '')[:40]}")
        return False
    subject = "Quick question about your post"
    return send_dm(username, subject, draft)


def process_pending_leads(max_dms: int = 3) -> int:
    """
    Go through demand_leads.json and DM strong leads not yet contacted.
    Returns count of DMs sent.
    """
    if not LEADS_FILE.exists():
        log("No leads file found")
        return 0

    leads = json.loads(LEADS_FILE.read_text())
    strong = [l for l in leads if l.get("score", 0) >= SCORE_THRESHOLD and not l.get("dm_sent")]
    log(f"Found {len(strong)} strong leads (score>={SCORE_THRESHOLD})")

    sent_count = 0
    for lead in strong[:max_dms]:
        if send_dm_to_lead(lead):
            lead["dm_sent"] = True
            sent_count += 1

    if sent_count:
        tmp = LEADS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(leads, indent=2, default=str))
        tmp.rename(LEADS_FILE)

    return sent_count


def get_status() -> dict:
    sent = _load_sent()
    return {
        "configured": is_configured(),
        "total_sent": len(sent),
        "dms_today": _dms_today(sent),
        "daily_limit": MAX_DMS_PER_DAY,
    }
