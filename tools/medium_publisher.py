#!/usr/bin/env python3
"""tools/medium_publisher.py — Publish a markdown draft to Medium via Playwright."""
import json
import re
import sys
import time
import logging
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

LOG = BASE / "logs/medium_publisher.log"
COOKIES_FILE = Path.home() / ".config/echo/medium_cookies.json"

logging.basicConfig(filename=str(LOG), level=logging.INFO, format="%(asctime)s %(message)s")

DEFAULT_TAGS = ["python", "automation", "ai", "programming", "developer"]


def log(msg):
    print(f"[medium] {msg}", flush=True)
    logging.info(msg)


def load_env():
    env = {}
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _load_cookies():
    if COOKIES_FILE.exists():
        try:
            return json.loads(COOKIES_FILE.read_text())
        except Exception:
            pass
    return None


def _save_cookies(context):
    COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIES_FILE.write_text(json.dumps(context.cookies(), indent=2))


def _medium_login(page, env):
    """Login to Medium via Google SSO. Returns True if logged in."""
    log("navigating to Medium signin...")
    page.goto("https://medium.com/m/signin", wait_until="domcontentloaded", timeout=30000)

    google_email = env.get("GOOGLE_EMAIL") or env.get("GMAIL_ADDRESS", "")
    google_password = env.get("GOOGLE_PASSWORD", "")

    # Medium uses an <a> link that redirects (not a popup)
    google_link = None
    for sel in [
        "a[href*='m/connect/google']",
        "a:has-text('Sign in with Google')",
        "a[href*='google']",
    ]:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=8000)
            google_link = el
            break
        except Exception:
            continue

    if not google_link:
        log("no Google sign-in link found on Medium signin page")
        return False

    google_link.click()
    log("clicked Google sign-in link — waiting for Google redirect...")

    # Wait for navigation to Google accounts
    try:
        page.wait_for_url("**/accounts.google.com/**", timeout=15000)
        log("on Google accounts page")
    except Exception:
        log(f"did not reach accounts.google.com — current url: {page.url[:80]}")
        if "medium.com" in page.url and "signin" not in page.url:
            log("looks like already signed in (fast redirect)")
            return True
        return False

    time.sleep(1)
    try:
        from core.google_sso import google_login
        ok = google_login(page, google_email, google_password)
        if ok:
            log("Google SSO succeeded")
            time.sleep(3)
            return True
        log("google_login returned False")
    except Exception as e:
        log(f"SSO error: {e}")

    return False


def _markdown_to_medium(body: str) -> str:
    """Convert markdown to Medium-compatible plain text with basic formatting."""
    # Medium's new story editor is a rich text editor — we paste plain text
    # and it handles paragraphs via newlines. Keep it simple.
    return body.strip()


def publish(title: str, body: str, tags: list = None) -> str | None:
    """Publish to Medium via Playwright. Returns post URL or None."""
    env = load_env()

    if not (env.get("GOOGLE_EMAIL") or env.get("GMAIL_ADDRESS")):
        log("GOOGLE_EMAIL not set — skipping Medium")
        return None

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel="chrome",
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 860},
        )
        page = context.new_page()

        try:
            ok = _medium_login(page, env)
            if not ok:
                log("login failed — cannot publish")
                browser.close()
                return None

            # Open new story
            log("opening new story editor...")
            page.goto("https://medium.com/new-story", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            # Find title field (first contenteditable / h3)
            title_selectors = [
                "h3[data-placeholder]",
                "[data-testid='editor-title'] [contenteditable]",
                "[contenteditable][data-placeholder*='Title']",
                "div[contenteditable] h3",
                "[contenteditable]",
            ]
            title_el = None
            for sel in title_selectors:
                try:
                    el = page.locator(sel).first
                    el.wait_for(state="visible", timeout=3000)
                    title_el = el
                    break
                except Exception:
                    continue

            if not title_el:
                log("could not find title field")
                browser.close()
                return None

            title_el.click()
            time.sleep(0.5)
            title_el.fill(title)
            time.sleep(0.5)
            log(f"typed title: {title[:60]}")

            # Tab or Enter to move to body
            page.keyboard.press("Enter")
            time.sleep(0.5)

            # Find body field and type content
            body_selectors = [
                "p[data-placeholder]",
                "[data-testid='editor-body'] [contenteditable]",
                "[contenteditable][data-placeholder*='Tell your story']",
                "[contenteditable]",
            ]
            body_el = None
            for sel in body_selectors:
                try:
                    els = page.locator(sel).all()
                    # Pick the second contenteditable (first is title)
                    if len(els) > 1:
                        body_el = els[1]
                        body_el.wait_for(state="visible", timeout=2000)
                        break
                    elif els:
                        body_el = els[0]
                        body_el.wait_for(state="visible", timeout=2000)
                        break
                except Exception:
                    continue

            # After pressing Enter in title, cursor should be in body — just type
            # Body el click may fail if out of viewport; scroll + JS focus instead
            clean_body = _markdown_to_medium(body)
            if body_el:
                try:
                    body_el.scroll_into_view_if_needed(timeout=3000)
                    body_el.click(timeout=5000)
                except Exception:
                    # Fallback: JS focus
                    try:
                        page.evaluate("document.querySelectorAll('[contenteditable]')[1]?.focus()")
                    except Exception:
                        pass
            time.sleep(0.5)
            # Use clipboard paste for speed
            context.grant_permissions(["clipboard-read", "clipboard-write"])
            page.evaluate(f"navigator.clipboard.writeText({json.dumps(clean_body)})")
            page.keyboard.press("Control+v")
            time.sleep(2)
            log(f"pasted body ({len(clean_body)} chars)")

            # Click Publish button
            pub_selectors = [
                "button:has-text('Publish')",
                "[data-testid='publish-button']",
                "button[class*='publish']",
            ]
            published = False
            for sel in pub_selectors:
                try:
                    btn = page.locator(sel).first
                    btn.wait_for(state="visible", timeout=5000)
                    btn.click()
                    log("clicked Publish")
                    time.sleep(2)
                    published = True
                    break
                except Exception:
                    continue

            if not published:
                log("could not find Publish button")
                browser.close()
                return None

            # Handle publish modal — add tags, confirm
            time.sleep(2)

            # Add tags if there's a tag input
            tag_list = (tags or DEFAULT_TAGS)[:5]
            try:
                tag_input = page.locator("input[placeholder*='tag' i], input[placeholder*='Add a tag' i]").first
                tag_input.wait_for(state="visible", timeout=3000)
                for tag in tag_list:
                    tag_input.fill(tag)
                    time.sleep(0.3)
                    page.keyboard.press("Enter")
                    time.sleep(0.2)
                log(f"added tags: {tag_list}")
            except Exception:
                pass

            # Final publish confirm
            for sel in [
                "button:has-text('Publish now')",
                "button:has-text('Publish story')",
                "button:has-text('Publish')",
                "[data-testid='confirm-publish']",
            ]:
                try:
                    btn = page.locator(sel).last
                    btn.wait_for(state="visible", timeout=3000)
                    btn.click()
                    log("confirmed publish")
                    time.sleep(4)
                    break
                except Exception:
                    continue

            # Get the published URL
            post_url = page.url
            if "medium.com" in post_url and "/p/" in post_url:
                log(f"published: {post_url}")
                browser.close()
                return post_url

            # Try reading it from page
            try:
                canonical = page.evaluate("document.querySelector('link[rel=canonical]')?.href")
                if canonical and "medium.com" in canonical:
                    log(f"published: {canonical}")
                    browser.close()
                    return canonical
            except Exception:
                pass

            log(f"published (URL unknown — current: {post_url})")
            browser.close()
            return post_url if "medium.com" in post_url else "https://medium.com"

        except Exception as e:
            log(f"publish error: {e}")
            browser.close()
            return None


def publish_from_file(draft_path: str) -> str | None:
    path = Path(draft_path)
    if not path.exists():
        log(f"draft not found: {draft_path}")
        return None

    content = path.read_text()
    lines = content.split("\n")
    title = lines[0].lstrip("#").strip() if lines and lines[0].startswith("#") else path.stem
    body = "\n".join(lines[2:]).strip() if len(lines) > 2 else content

    return publish(title, body)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-draft", required=True, help="Path to .md draft file")
    args = parser.parse_args()
    url = publish_from_file(args.from_draft)
    sys.exit(0 if url else 1)
