#!/usr/bin/env python3
"""
tools/fiverr_buyer_requests.py — Monitor Fiverr Buyer Requests and draft responses.

Logs into Fiverr via Playwright, scrapes available buyer requests, scores them
against the gig, drafts offers using the LLM, and sends top matches to Telegram
for Andrew to review. Andrew approves; he submits manually.

Runs every 3 hours via echo-fiverr-requests.timer.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

LOG = BASE / "logs/fiverr_requests.log"
SEEN_FILE = BASE / "memory/fiverr_seen_requests.json"
COOKIES_FILE = Path.home() / ".config/echo/fiverr_cookies.json"

GIG_KEYWORDS = [
    "python", "automation", "script", "bot", "ai", "local", "tool",
    "workflow", "scraper", "scraping", "automate", "custom", "software",
    "developer", "coding", "program", "app", "integration", "api",
]
MIN_SCORE = 3  # keyword hits required to consider a request relevant


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[fiverr] {msg}", flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def _get_env():
    env = {}
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except Exception:
            pass
    return set()


def _save_seen(seen: set):
    tmp = SEEN_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(list(seen), indent=2))
    tmp.rename(SEEN_FILE)


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


def score_request(title: str, description: str) -> int:
    text = (title + " " + description).lower()
    return sum(1 for kw in GIG_KEYWORDS if kw in text)


def draft_response(title: str, description: str, budget: str) -> str:
    try:
        from core.providers.router import call_ollama
        prompt = (
            f"You are Andrew, a Python developer offering local AI automation on Fiverr.\n"
            f"Your gig: 'Build a local AI automation system in Python that runs on your hardware'\n\n"
            f"Write a short, friendly Fiverr buyer request response (under 150 words).\n"
            f"Be specific to their request. Mention you build in Python, runs locally, no monthly fees.\n"
            f"End with a clear call to action.\n\n"
            f"Buyer Request Title: {title}\n"
            f"Buyer Description: {description}\n"
            f"Budget: {budget}\n\n"
            f"Response:"
        )
        return call_ollama(prompt, model="llama3.1:latest", timeout=60)
    except Exception as e:
        return f"[draft failed: {e}]"


def login(page, env):
    log("logging into Fiverr...")
    page.goto("https://www.fiverr.com/login", wait_until="networkidle", timeout=30000)
    time.sleep(2)

    try:
        page.fill('input[name="email"]', env["FIVERR_USERNAME"], timeout=10000)
        page.fill('input[name="password"]', env["FIVERR_PASSWORD"], timeout=10000)
        page.click('button[type="submit"]', timeout=10000)
        page.wait_for_url("**/fiverr.com/**", timeout=20000)
        time.sleep(3)
        log("login successful")
        return True
    except Exception as e:
        log(f"login failed: {e}")
        return False


def get_buyer_requests(page):
    """Navigate to buyer requests and extract listings."""
    requests_found = []

    urls_to_try = [
        "https://www.fiverr.com/requests/buyer_requests",
        "https://www.fiverr.com/requests",
    ]

    for url in urls_to_try:
        try:
            log(f"trying {url}")
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(3)

            # Check if we landed on a valid requests page
            if "requests" not in page.url and "brief" not in page.url:
                log(f"redirected away from {url} — skipping")
                continue

            # Try to extract request cards
            cards = page.query_selector_all("[class*='request-row'], [class*='buyer-request'], [data-testid*='request']")
            if not cards:
                # Broader fallback selector
                cards = page.query_selector_all("li[class*='request'], div[class*='request-item']")

            log(f"found {len(cards)} request cards at {url}")

            for card in cards:
                try:
                    title = card.query_selector("[class*='title'], h3, h4")
                    desc = card.query_selector("[class*='description'], [class*='desc'], p")
                    budget = card.query_selector("[class*='budget'], [class*='price']")

                    title_text = title.inner_text().strip() if title else ""
                    desc_text = desc.inner_text().strip() if desc else ""
                    budget_text = budget.inner_text().strip() if budget else "unspecified"

                    if title_text:
                        requests_found.append({
                            "title": title_text,
                            "description": desc_text,
                            "budget": budget_text,
                            "source_url": url,
                        })
                except Exception:
                    continue

            if requests_found:
                break

        except Exception as e:
            log(f"error fetching {url}: {e}")
            continue

    return requests_found


def run():
    log("fiverr buyer requests starting")
    env = _get_env()

    if not env.get("FIVERR_USERNAME") or not env.get("FIVERR_PASSWORD"):
        log("FIVERR_USERNAME/PASSWORD not configured — exiting")
        return

    seen = _load_seen()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Restore saved cookies to skip login if session is still valid
        saved_cookies = _load_cookies()
        if saved_cookies:
            try:
                context.add_cookies(saved_cookies)
                log("restored saved session cookies")
            except Exception:
                pass

        page = context.new_page()

        # Check if session is still valid
        page.goto("https://www.fiverr.com", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        logged_in = page.query_selector("[class*='profile-image'], [data-testid='header-profile']") is not None

        if not logged_in:
            if not login(page, env):
                log("could not log in — aborting")
                browser.close()
                return
            _save_cookies(context)
        else:
            log("session still valid — skipped login")

        requests = get_buyer_requests(page)
        browser.close()

    log(f"scraped {len(requests)} total requests")

    new_count = 0
    sent_count = 0

    for req in requests:
        req_id = req["title"][:60]
        if req_id in seen:
            continue

        new_count += 1
        seen.add(req_id)

        score = score_request(req["title"], req["description"])
        log(f"score={score} | {req['title'][:50]}")

        if score < MIN_SCORE:
            continue

        draft = draft_response(req["title"], req["description"], req["budget"])

        message = (
            f"🎯 Fiverr Buyer Request (score: {score}/10)\n\n"
            f"*{req['title']}*\n"
            f"Budget: {req['budget']}\n\n"
            f"{req['description'][:300]}{'...' if len(req['description']) > 300 else ''}\n\n"
            f"---\n*Draft Response:*\n{draft}\n\n"
            f"Review at: {req['source_url']}"
        )

        try:
            from core.notifier import notify_telegram
            notify_telegram("Fiverr Lead", message)
            sent_count += 1
            log(f"sent to Telegram: {req['title'][:50]}")
        except Exception as e:
            log(f"telegram notify failed: {e}")

        time.sleep(2)

    _save_seen(seen)
    log(f"done — {new_count} new, {sent_count} sent to Telegram")


if __name__ == "__main__":
    run()
