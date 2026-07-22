#!/usr/bin/env python3
"""
tools/fiverr_inbox_responder.py — Monitors Fiverr inbox and sends LLM-drafted replies.

Flow: login → read unread threads → LLM drafts reply → sends it → marks handled.
Runs every 30 min via echo-fiverr-inbox.timer.
Max 10 replies/day. Skips threads already replied to by Echo.
"""
import json
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

LOG = BASE / "logs/fiverr_inbox.log"
REPLIED_FILE = BASE / "memory/fiverr_inbox_replied.json"
COOKIES_FILE = Path.home() / ".config/echo/fiverr_cookies.json"
MAX_REPLIES_PER_DAY = 10

logging.basicConfig(filename=str(LOG), level=logging.INFO, format="%(asctime)s %(message)s")


def log(msg):
    print(f"[fiverr_inbox] {msg}", flush=True)
    logging.info(msg)


def _get_env():
    env = {}
    for line in (Path.home() / ".config/echo/golem.env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def _load_replied():
    if REPLIED_FILE.exists():
        try:
            return json.loads(REPLIED_FILE.read_text())
        except Exception:
            pass
    return []


def _save_replied(replied):
    tmp = REPLIED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(replied, indent=2, default=str))
    tmp.rename(REPLIED_FILE)


def _replies_today(replied):
    cutoff = (datetime.now() - timedelta(days=1)).isoformat()
    return sum(1 for r in replied if r.get("replied_at", "") >= cutoff)


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


def fiverr_login(page, env):
    log("checking Fiverr session...")
    page.goto("https://www.fiverr.com", wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)

    logged_in = bool(
        page.query_selector("[data-testid='header-profile']") or
        page.query_selector("[class*='profile-image']") or
        page.query_selector("a[href*='/inbox']")
    )
    if logged_in:
        log("session valid — skipped login")
        return True

    log("logging in via Google SSO...")
    page.goto("https://www.fiverr.com/login", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    google_email = env.get("GOOGLE_EMAIL") or env.get("GMAIL_ADDRESS", "")
    google_password = env.get("GOOGLE_PASSWORD", "")
    if google_email and google_password:
        try:
            from core.google_sso import handle_google_sso_button
            ok = handle_google_sso_button(page, google_email, google_password)
            if ok:
                time.sleep(4)
                log("Google SSO login succeeded")
                return True
        except Exception as e:
            log(f"Google SSO error: {e}")

    log("login failed — no valid credentials")
    return False


def draft_reply(thread_subject: str, messages: list[str]) -> str:
    try:
        from core.providers.router import call_ollama
        history = "\n".join(f"  - {m[:200]}" for m in messages[-4:])
        prompt = (
            f"You are Andrew, a Python developer on Fiverr specializing in local AI automation.\n"
            f"Your gig: 'Build a local AI automation system in Python that runs on your hardware'\n\n"
            f"Reply to this Fiverr inbox thread. Be friendly, professional, and specific.\n"
            f"Keep it under 120 words. Address their question directly.\n"
            f"Offer to hop on a quick requirements call if needed.\n\n"
            f"Thread subject: {thread_subject}\n"
            f"Recent messages:\n{history}\n\n"
            f"Your reply:"
        )
        reply = call_ollama(prompt, model="qwen2.5:7b", timeout=60)
        return reply.strip() if reply else ""
    except Exception as e:
        log(f"draft_reply LLM error: {e}")
        return ""


def process_inbox(page):
    log("navigating to inbox...")
    page.goto("https://www.fiverr.com/inbox", wait_until="networkidle", timeout=30000)
    time.sleep(3)

    replied = _load_replied()
    replied_ids = {r["thread_id"] for r in replied}

    if _replies_today(replied) >= MAX_REPLIES_PER_DAY:
        log(f"daily reply limit reached ({MAX_REPLIES_PER_DAY}) — stopping")
        return replied

    # Find unread conversation threads
    thread_selectors = [
        "[class*='conversation-item']",
        "[class*='inbox-item']",
        "[class*='message-thread']",
        "li[class*='thread']",
        "[data-testid*='conversation']",
    ]

    threads = []
    for sel in thread_selectors:
        found = page.query_selector_all(sel)
        if found:
            threads = found
            log(f"found {len(threads)} threads using {sel}")
            break

    if not threads:
        log("no threads found — inbox may be empty or selector needs update")
        return replied

    new_replies = 0
    for thread in threads[:10]:  # process at most 10 threads per run
        try:
            # Check for unread indicator
            unread = (
                thread.query_selector("[class*='unread']") or
                thread.query_selector("[class*='badge']") or
                thread.query_selector("[class*='new']")
            )

            # Get thread ID from href or data attribute
            link = thread.query_selector("a[href*='/inbox']") or thread.query_selector("a")
            thread_href = link.get_attribute("href") if link else ""
            thread_id = thread_href.split("/")[-1] if thread_href else ""

            if not thread_id or thread_id in replied_ids:
                continue

            if not unread:
                continue

            # Open the thread
            thread.click()
            time.sleep(2)

            # Read message content
            msg_selectors = [
                "[class*='message-body']",
                "[class*='msg-content']",
                "[class*='bubble-content']",
                "p[class*='message']",
            ]
            messages = []
            for sel in msg_selectors:
                els = page.query_selector_all(sel)
                if els:
                    messages = [el.inner_text().strip() for el in els[-4:] if el.inner_text().strip()]
                    break

            # Get thread subject/title
            subject_el = (
                page.query_selector("[class*='thread-title']") or
                page.query_selector("[class*='conversation-title']") or
                page.query_selector("h1") or
                page.query_selector("h2")
            )
            subject = subject_el.inner_text().strip() if subject_el else "Fiverr inquiry"

            if not messages:
                log(f"thread {thread_id}: no messages extracted — skipping")
                continue

            log(f"drafting reply for thread {thread_id}: {subject[:50]}")
            reply_text = draft_reply(subject, messages)

            if not reply_text or len(reply_text) < 20:
                log(f"thread {thread_id}: LLM reply too short — skipping")
                continue

            # Find reply input
            reply_selectors = [
                "textarea[placeholder*='reply' i]",
                "textarea[placeholder*='message' i]",
                "textarea[class*='reply']",
                "div[contenteditable='true']",
                "textarea",
            ]
            reply_input = None
            for sel in reply_selectors:
                try:
                    el = page.locator(sel).last
                    el.wait_for(state="visible", timeout=3000)
                    reply_input = el
                    break
                except Exception:
                    continue

            if not reply_input:
                log(f"thread {thread_id}: no reply input found")
                continue

            reply_input.fill(reply_text)
            time.sleep(1)

            # Send the reply
            send_selectors = [
                "button[type='submit']",
                "button[class*='send']",
                "button[aria-label*='send' i]",
                "[data-testid*='send']",
            ]
            sent = False
            for sel in send_selectors:
                try:
                    btn = page.locator(sel).last
                    btn.wait_for(state="visible", timeout=2000)
                    btn.click()
                    sent = True
                    break
                except Exception:
                    continue

            if not sent:
                page.keyboard.press("Control+Enter")
                sent = True

            time.sleep(2)

            record = {
                "thread_id": thread_id,
                "subject": subject[:100],
                "reply_preview": reply_text[:120],
                "replied_at": datetime.now().isoformat(),
            }
            replied.append(record)
            replied_ids.add(thread_id)
            new_replies += 1
            log(f"replied to thread {thread_id}: {subject[:40]}")

            if _replies_today(replied) >= MAX_REPLIES_PER_DAY:
                log("daily reply limit reached — stopping")
                break

            time.sleep(3)

        except Exception as e:
            log(f"thread processing error: {e}")
            continue

    log(f"inbox run done — {new_replies} replies sent")
    return replied


def run():
    log("starting")
    env = _get_env()

    if not (env.get("GOOGLE_PASSWORD") or env.get("FIVERR_PASSWORD")):
        log("no login credentials — exiting")
        return

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )

        saved = _load_cookies()
        if saved:
            try:
                context.add_cookies(saved)
            except Exception:
                pass

        page = context.new_page()

        try:
            ok = fiverr_login(page, env)
            if not ok:
                log("login failed — aborting")
                browser.close()
                return

            _save_cookies(context)
            replied = process_inbox(page)
            _save_replied(replied)

        except Exception as e:
            log(f"run error: {e}")
        finally:
            browser.close()

    log("done")


if __name__ == "__main__":
    run()
