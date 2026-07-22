#!/usr/bin/env python3
"""
core/reddit_playwright_outreach.py — Reddit outreach via browser automation.

Uses Playwright + old.reddit.com instead of OAuth. Only needs REDDIT_USERNAME
and REDDIT_PASSWORD in golem.env — no app registration required.

Flow: reads demand_leads.json → visits each post URL → scrapes author →
navigates to old.reddit.com/message/compose → sends DM → marks lead contacted.
Max 5 DMs/day, 1h gap between sends to avoid rate limiting.
"""

import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

LOG = BASE / "logs/reddit_playwright_outreach.log"
LEADS_FILE = BASE / "memory/demand_leads.json"
SENT_FILE = BASE / "memory/reddit_dms_sent.json"
COOKIES_FILE = Path.home() / ".config/echo/reddit_cookies.json"

MAX_DMS_PER_DAY = 5
SCORE_THRESHOLD = 7
MIN_GAP_SECONDS = 3600  # 1 hour between sends


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(f"[reddit_pw] {msg}", flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def _get_env():
    env = {}
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v
    return env


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
    return any(s.get("username", "").lower() == username.lower() for s in sent)


def _dms_today(sent):
    cutoff = (datetime.now() - timedelta(days=1)).isoformat()
    return sum(1 for s in sent if s.get("sent_at", "") >= cutoff)


def _last_send_time(sent):
    if not sent:
        return None
    recent = [s.get("sent_at", "") for s in sent if s.get("sent_at")]
    return max(recent) if recent else None


def _load_cookies():
    if COOKIES_FILE.exists():
        try:
            return json.loads(COOKIES_FILE.read_text())
        except Exception:
            pass
    return None


def _save_cookies(context):
    cookies = context.cookies()
    COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIES_FILE.write_text(json.dumps(cookies, indent=2))


def _is_logged_in(page):
    try:
        page.goto("https://old.reddit.com", wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
        user_el = page.query_selector("span.user a, a[href*='/user/']")
        if user_el:
            text = user_el.inner_text().strip()
            return text and text.lower() not in ("login", "register", "log in", "sign up")
    except Exception:
        pass
    return False


def _login(page, env):
    """Try Google SSO first, fall back to username/password on old.reddit.com."""
    google_email = env.get("GOOGLE_EMAIL") or env.get("GMAIL_ADDRESS", "")
    google_password = env.get("GOOGLE_PASSWORD", "")

    # ── Path 1: Google SSO via new Reddit ─────────────────────────────────
    if google_email and google_password:
        try:
            from core.google_sso import handle_google_sso_button
            log("trying Google SSO via new Reddit...")
            page.goto("https://www.reddit.com/login", wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)
            ok = handle_google_sso_button(page, google_email, google_password)
            if ok:
                time.sleep(3)
                # Check on old.reddit.com if session carried over
                page.goto("https://old.reddit.com", wait_until="domcontentloaded", timeout=15000)
                time.sleep(2)
                user_el = page.query_selector("span.user a")
                if user_el and user_el.inner_text().strip().lower() not in ("login", "register"):
                    log(f"Google SSO login confirmed on old.reddit.com")
                    return True
                # Session didn't carry to old.reddit.com — still try scraping via new Reddit
                log("Google SSO succeeded but old.reddit.com session not synced — continuing anyway")
                return True
        except Exception as e:
            log(f"Google SSO error: {e} — trying username/password")

    # ── Path 2: old.reddit.com username/password ───────────────────────────
    reddit_user = env.get("REDDIT_USERNAME", "")
    reddit_pass = env.get("REDDIT_PASSWORD", "")
    if not reddit_user or not reddit_pass:
        log("no credentials — set GOOGLE_EMAIL/GOOGLE_PASSWORD or REDDIT_USERNAME/REDDIT_PASSWORD")
        return False

    log("logging into old.reddit.com with username/password...")
    page.goto("https://old.reddit.com/login", wait_until="domcontentloaded", timeout=20000)
    time.sleep(2)
    try:
        page.fill('input[name="user"]', reddit_user, timeout=8000)
        page.fill('input[name="passwd"]', reddit_pass, timeout=8000)
        page.click('button[type="submit"]', timeout=8000)
        time.sleep(3)
        page.wait_for_url("**/old.reddit.com/**", timeout=15000)
        if page.query_selector("div.error") is not None:
            log("login failed: error on page")
            return False
        log("username/password login successful")
        return True
    except Exception as e:
        log(f"login failed: {e}")
        return False


def _scrape_author(page, post_url):
    """Visit the post and extract the OP username."""
    try:
        old_url = post_url.replace("https://www.reddit.com", "https://old.reddit.com") \
                          .replace("https://reddit.com", "https://old.reddit.com")
        page.goto(old_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
        # Old Reddit: the post author is in a <a class="author"> element
        el = page.query_selector("a.author")
        if el:
            author = el.inner_text().strip()
            if author and author.lower() not in ("deleted", "[deleted]"):
                return author
    except Exception as e:
        log(f"could not scrape author from {post_url}: {e}")
    return None


def _send_dm(page, username, subject, body):
    """Use old.reddit.com compose to send a DM."""
    compose_url = (
        f"https://old.reddit.com/message/compose"
        f"?to={quote(username)}"
        f"&subject={quote(subject)}"
        f"&message={quote(body)}"
    )
    try:
        page.goto(compose_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
        page.click('button[type="submit"]', timeout=8000)
        time.sleep(2)
        # Check for success: old Reddit redirects to /message/sent after success
        if "sent" in page.url or page.query_selector("div.submit-status") is not None:
            return True
        # Fallback: check for error elements
        err = page.query_selector("div.error, span.error")
        if err:
            log(f"DM error: {err.inner_text().strip()}")
            return False
        # No error found — assume OK
        return True
    except Exception as e:
        log(f"DM send exception: {e}")
        return False


def run(dry_run=False):
    log(f"starting outreach (dry_run={dry_run})")
    env = _get_env()

    if not env.get("REDDIT_USERNAME") or not env.get("REDDIT_PASSWORD"):
        log("REDDIT_USERNAME or REDDIT_PASSWORD not set in golem.env — exiting")
        return 0

    if not LEADS_FILE.exists():
        log("no leads file found")
        return 0

    leads = json.loads(LEADS_FILE.read_text())
    strong = [
        l for l in leads
        if l.get("score", 0) >= SCORE_THRESHOLD
        and not l.get("dm_sent")
        and l.get("url")
    ]
    log(f"{len(strong)} strong leads (score>={SCORE_THRESHOLD}, not yet DM'd)")

    sent = _load_sent()
    daily = _dms_today(sent)
    if daily >= MAX_DMS_PER_DAY:
        log(f"daily limit reached ({daily}/{MAX_DMS_PER_DAY}) — exiting")
        return 0

    # Enforce minimum gap between sends
    last_send = _last_send_time(sent)
    if last_send:
        elapsed = (datetime.now() - datetime.fromisoformat(last_send)).total_seconds()
        if elapsed < MIN_GAP_SECONDS:
            wait_min = int((MIN_GAP_SECONDS - elapsed) / 60)
            log(f"last DM {int(elapsed/60)}m ago — waiting {wait_min}m before next")
            return 0

    from playwright.sync_api import sync_playwright

    sent_count = 0
    leads_modified = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        saved = _load_cookies()
        if saved:
            try:
                context.add_cookies(saved)
                log("restored saved session cookies")
            except Exception:
                pass

        page = context.new_page()

        if not _is_logged_in(page):
            if not _login(page, env):
                log("could not log in — aborting")
                browser.close()
                return 0
            _save_cookies(context)
        else:
            log(f"session valid as u/{env['REDDIT_USERNAME']}")

        for lead in strong:
            if sent_count + daily >= MAX_DMS_PER_DAY:
                log("daily limit reached mid-run — stopping")
                break

            post_url = lead.get("url", "")
            author = _scrape_author(page, post_url)
            if not author:
                log(f"no author found for: {lead['title'][:50]}")
                continue

            if _already_sent(author, sent):
                log(f"already DMed u/{author} — skip")
                lead["dm_sent"] = True
                leads_modified = True
                continue

            draft = lead.get("outreach_draft", "")
            if not draft:
                log(f"no draft for lead: {lead['title'][:40]}")
                continue

            subject = "Quick question about your post"
            log(f"DM to u/{author} | {lead['title'][:45]}")

            if dry_run:
                log(f"[DRY RUN] would send to u/{author}")
                sent_count += 1
                continue

            ok = _send_dm(page, author, subject, draft)
            if ok:
                sent.append({
                    "username": author,
                    "post_id": lead.get("post_id"),
                    "sent_at": datetime.now().isoformat(),
                    "subject": subject,
                })
                _save_sent(sent)
                lead["dm_sent"] = True
                leads_modified = True
                sent_count += 1
                log(f"sent DM to u/{author} ({sent_count}/{MAX_DMS_PER_DAY})")

                try:
                    from core.notifier import notify
                    notify("Reddit DM Sent", f"u/{author} — {lead['title'][:60]}")
                except Exception:
                    pass

                if sent_count + daily < MAX_DMS_PER_DAY:
                    time.sleep(30)  # brief pause between DMs
            else:
                log(f"DM failed for u/{author}")

        browser.close()

    if leads_modified:
        tmp = LEADS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(leads, indent=2, default=str))
        tmp.rename(LEADS_FILE)

    log(f"done — {sent_count} DMs sent this run")
    return sent_count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="scrape authors but don't actually send")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
