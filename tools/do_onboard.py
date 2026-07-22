#!/usr/bin/env python3
"""tools/do_onboard.py — DigitalOcean account setup, referral link + API token extraction.

Usage:
  python tools/do_onboard.py --signup   # Phase 1: create account via Google SSO
  python tools/do_onboard.py --extract  # Phase 2: extract referral link + API token (run after account is verified)

Phase 1 stops at phone/CC walls and sends a Telegram notification with a screenshot.
Phase 2 assumes the account exists and is verified.
"""
import argparse
import json
import os
import sys
import time
import secrets
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

LOG = BASE / "logs/do_onboard.log"
STATE_FILE = BASE / "memory/do_onboard_state.json"
AFFILIATE_FILE = BASE / "memory/affiliate_links.json"
GOLEM_ENV = Path.home() / ".config/echo/golem.env"
SCREENSHOTS_DIR = BASE / "logs/screenshots"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[do_onboard] {msg}", flush=True)


def load_env():
    env = {}
    if GOLEM_ENV.exists():
        for line in GOLEM_ENV.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def notify(title, msg):
    try:
        from core.notifier import notify as _notify
        _notify(title, msg)
    except Exception as e:
        log(f"notify failed: {e}")


def screenshot(page, name):
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOTS_DIR / f"do_{name}_{datetime.now().strftime('%H%M%S')}.png"
    try:
        page.screenshot(path=str(path))
        log(f"screenshot saved: {path.name}")
    except Exception as e:
        log(f"screenshot failed: {e}")
    return str(path)


def save_state(state: dict):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(STATE_FILE)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _google_login(page, env):
    """Complete Google SSO if redirected to accounts.google.com."""
    try:
        page.wait_for_url("**/accounts.google.com/**", timeout=12000)
        log("on Google accounts page")
    except Exception:
        current = page.url
        log(f"did not reach accounts.google.com — url: {current[:80]}")
        return "cloud.digitalocean.com" in current

    time.sleep(1)
    try:
        from core.google_sso import google_login
        ok = google_login(
            page,
            env.get("GOOGLE_EMAIL") or env.get("GMAIL_ADDRESS", ""),
            env.get("GOOGLE_PASSWORD", ""),
        )
        if ok:
            log("Google SSO succeeded")
            time.sleep(4)
            return True
        log("google_login returned False")
    except Exception as e:
        log(f"SSO error: {e}")
    return False


def _detect_wall(page) -> str:
    """Detect what manual step is blocking account activation. Returns wall type or 'ok'."""
    url = page.url.lower()
    html = ""
    try:
        html = page.content().lower()
    except Exception:
        pass

    if "phone" in url or "verify" in url or "phone" in html:
        return "phone"
    if "payment" in url or "billing" in url or "credit" in html or "card" in html:
        return "payment"
    if "captcha" in html or "recaptcha" in html or "hcaptcha" in html:
        return "captcha"
    if "cloud.digitalocean.com" in url and "register" not in url and "login" not in url:
        return "ok"
    return "unknown"


def run_signup():
    """Phase 1: open DigitalOcean signup via Google SSO, stop at manual walls."""
    env = load_env()
    email = env.get("GOOGLE_EMAIL") or env.get("GMAIL_ADDRESS", "")
    if not email:
        log("GOOGLE_EMAIL not set in golem.env — cannot proceed")
        sys.exit(1)

    log(f"starting DO signup for {email}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel="chrome",
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            log("navigating to DigitalOcean signup...")
            page.goto("https://cloud.digitalocean.com/registrations/new", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            screenshot(page, "signup_loaded")

            # Find Google sign-in button
            google_btn = None
            for sel in [
                "a[href*='google']",
                "button:has-text('Google')",
                "[data-testid*='google']",
                "a:has-text('Sign up with Google')",
                "a:has-text('Google')",
            ]:
                try:
                    el = page.locator(sel).first
                    el.wait_for(state="visible", timeout=5000)
                    google_btn = el
                    log(f"found Google button: {sel}")
                    break
                except Exception:
                    continue

            if not google_btn:
                screenshot(page, "no_google_btn")
                notify("DO Setup: manual step needed", f"Could not find Google sign-up button. Screenshot saved. URL: {page.url[:80]}")
                log("no Google button found — manual signup required")
                browser.close()
                return

            # Check terms/TOS checkbox before clicking Google
            for tos_sel in [
                "input[type='checkbox']",
                "[name*='terms']",
                "[name*='agree']",
                "label:has-text('agree')",
                "label:has-text('Terms')",
            ]:
                try:
                    el = page.locator(tos_sel).first
                    el.wait_for(state="visible", timeout=3000)
                    el.check()
                    log(f"checked TOS checkbox: {tos_sel}")
                    time.sleep(0.5)
                    break
                except Exception:
                    continue

            google_btn.click()
            log("clicked Google signup button")

            ok = _google_login(page, env)
            if not ok:
                screenshot(page, "sso_failed")
                notify("DO Setup: Google SSO failed", f"Sign in failed. URL: {page.url[:80]}")
                browser.close()
                return

            # Wait a moment for DO to process the new account
            time.sleep(5)
            screenshot(page, "after_sso")
            wall = _detect_wall(page)
            log(f"post-SSO wall: {wall} | url: {page.url[:80]}")

            if wall == "ok":
                log("account created and active — running extract phase")
                browser.close()
                save_state({"status": "account_ready", "updated_at": datetime.now().isoformat()})
                run_extract_with_browser(env)
                return

            if wall == "phone":
                screenshot(page, "phone_wall")
                notify(
                    "DO Setup: phone verification needed",
                    "Echo created your DigitalOcean account via Google. "
                    "Please open cloud.digitalocean.com, complete phone verification, "
                    "then reply DOEXTRACT on Telegram.",
                )
                save_state({"status": "needs_phone", "updated_at": datetime.now().isoformat()})
                log("stopping — phone verification required. Reply DOEXTRACT on Telegram when done.")

            elif wall == "payment":
                screenshot(page, "payment_wall")
                notify(
                    "DO Setup: payment method needed",
                    "Echo created your DigitalOcean account via Google. "
                    "Please add a payment method at cloud.digitalocean.com/billing, "
                    "then reply DOEXTRACT on Telegram.",
                )
                save_state({"status": "needs_payment", "updated_at": datetime.now().isoformat()})
                log("stopping — payment method required. Reply DOEXTRACT on Telegram when done.")

            elif wall == "captcha":
                screenshot(page, "captcha_wall")
                notify(
                    "DO Setup: CAPTCHA needed",
                    "Echo hit a CAPTCHA during DigitalOcean signup. "
                    "Please complete signup manually at cloud.digitalocean.com, "
                    "then reply DOEXTRACT on Telegram.",
                )
                save_state({"status": "needs_captcha", "updated_at": datetime.now().isoformat()})

            else:
                screenshot(page, "unknown_wall")
                notify(
                    "DO Setup: manual step needed",
                    f"Echo got stuck at: {page.url[:80]}. "
                    "Please complete any remaining steps at cloud.digitalocean.com, "
                    "then reply DOEXTRACT on Telegram.",
                )
                save_state({"status": "unknown_wall", "url": page.url, "updated_at": datetime.now().isoformat()})

        except Exception as e:
            log(f"signup error: {e}")
            try:
                screenshot(page, "error")
            except Exception:
                pass
            notify("DO Setup failed", f"Error during signup: {str(e)[:100]}")
        finally:
            browser.close()


def run_extract_with_browser(env=None):
    """Phase 2 (internal): reuse existing browser session or open fresh one."""
    if env is None:
        env = load_env()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel="chrome",
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            # Login first
            log("logging into DigitalOcean...")
            page.goto("https://cloud.digitalocean.com/login", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            # Try Google login button
            for sel in ["a[href*='google']", "button:has-text('Google')", "a:has-text('Google')"]:
                try:
                    el = page.locator(sel).first
                    el.wait_for(state="visible", timeout=5000)
                    el.click()
                    log(f"clicked Google login: {sel}")
                    break
                except Exception:
                    continue

            ok = _google_login(page, env)
            if not ok:
                # May already be logged in
                if "cloud.digitalocean.com" in page.url and "login" not in page.url:
                    log("already logged in")
                    ok = True

            if not ok:
                screenshot(page, "extract_login_failed")
                notify("DO Extract failed", f"Could not log in. URL: {page.url[:80]}")
                browser.close()
                return

            referral_url = _extract_referral(page)
            api_token = _create_api_token(page)

            browser.close()

            if referral_url:
                _update_affiliate_links(referral_url)
            if api_token:
                _update_golem_env(api_token)

            save_state({
                "status": "complete",
                "referral_extracted": bool(referral_url),
                "token_created": bool(api_token),
                "updated_at": datetime.now().isoformat(),
            })

            parts = []
            if referral_url:
                parts.append(f"Referral link: {referral_url}")
            if api_token:
                parts.append("API token saved to golem.env — MCP server is now active")
            if not parts:
                parts.append("Nothing extracted — check logs/do_onboard.log")

            notify("DO Setup complete", "\n".join(parts))
            log("extract complete")

        except Exception as e:
            log(f"extract error: {e}")
            try:
                screenshot(page, "extract_error")
            except Exception:
                pass
            notify("DO Extract failed", str(e)[:150])
            browser.close()


def _extract_referral(page) -> str | None:
    """Navigate to referral page and extract the referral URL."""
    log("navigating to referral page...")
    try:
        page.goto("https://cloud.digitalocean.com/account/referrals", wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)
        screenshot(page, "referral_page")

        # Look for refcode in page content
        html = page.content()
        import re

        # Try to find the referral URL directly in the page
        patterns = [
            r'https://www\.digitalocean\.com/\?refcode=[A-Za-z0-9]+',
            r'digitalocean\.com/\?refcode=([A-Za-z0-9]+)',
            r'refcode["\s:=]+([A-Za-z0-9]{8,})',
        ]
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                if "https" in pat:
                    url = m.group(0)
                else:
                    code = m.group(1)
                    url = f"https://www.digitalocean.com/?refcode={code}"
                log(f"found referral URL: {url}")
                return url

        # Try clipboard copy button
        for sel in [
            "button:has-text('Copy')",
            "[data-testid*='copy']",
            "input[value*='refcode']",
            "input[readonly]",
        ]:
            try:
                el = page.locator(sel).first
                el.wait_for(state="visible", timeout=4000)
                val = el.get_attribute("value") or ""
                if "refcode" in val:
                    log(f"referral URL from input: {val}")
                    return val
                el.click()
                time.sleep(1)
                # re-check page after click
                html2 = page.content()
                for pat in patterns:
                    m = re.search(pat, html2)
                    if m:
                        code = m.group(1) if "refcode=" not in pat else m.group(0)
                        url = f"https://www.digitalocean.com/?refcode={code}" if "https" not in code else code
                        log(f"referral URL after click: {url}")
                        return url
            except Exception:
                continue

        log("referral URL not found on page")
        return None
    except Exception as e:
        log(f"referral extraction error: {e}")
        return None


def _create_api_token(page) -> str | None:
    """Navigate to API tokens page and create a new token named 'Echo'."""
    import re
    log("navigating to API tokens page...")
    try:
        page.goto("https://cloud.digitalocean.com/account/api/tokens", wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)
        screenshot(page, "api_tokens_page")

        # Check if Echo token already exists
        html = page.content()
        if "Echo" in html:
            log("Echo token may already exist — skipping creation")
            return None

        # Click Generate New Token
        for sel in [
            "button:has-text('Generate New Token')",
            "a:has-text('Generate New Token')",
            "button:has-text('Generate')",
            "[data-testid*='generate']",
        ]:
            try:
                el = page.locator(sel).first
                el.wait_for(state="visible", timeout=5000)
                el.click()
                log(f"clicked generate: {sel}")
                time.sleep(2)
                break
            except Exception:
                continue

        # Fill in token name
        for sel in ["input[placeholder*='name']", "input[name*='name']", "input[type='text']"]:
            try:
                el = page.locator(sel).first
                el.wait_for(state="visible", timeout=5000)
                el.fill("Echo")
                log("filled token name: Echo")
                time.sleep(1)
                break
            except Exception:
                continue

        # Set expiration to No expiry if available
        for sel in ["select[name*='expir']", "select"]:
            try:
                el = page.locator(sel).first
                el.wait_for(state="visible", timeout=3000)
                el.select_option(label="No expiry")
                log("set no expiry")
                break
            except Exception:
                break

        # Click Generate / Create
        for sel in [
            "button:has-text('Generate Token')",
            "button[type='submit']",
            "button:has-text('Create')",
        ]:
            try:
                el = page.locator(sel).first
                el.wait_for(state="visible", timeout=5000)
                el.click()
                log(f"clicked create: {sel}")
                time.sleep(3)
                break
            except Exception:
                continue

        # Extract token from page (shown once)
        screenshot(page, "token_created")
        html2 = page.content()
        token_patterns = [
            r'dop_v1_[a-f0-9]{64}',
            r'[a-f0-9]{64}',
        ]
        for pat in token_patterns:
            m = re.search(pat, html2)
            if m:
                token = m.group(0)
                log(f"API token extracted: {token[:12]}...")
                return token

        # Try to find token in input field
        for sel in ["input[readonly]", "input[type='text'][value]", "code"]:
            try:
                el = page.locator(sel).first
                el.wait_for(state="visible", timeout=3000)
                val = el.inner_text() if sel == "code" else el.get_attribute("value") or ""
                if len(val) > 20:
                    log(f"token from element ({sel}): {val[:12]}...")
                    return val
            except Exception:
                continue

        log("could not extract token from page")
        return None

    except Exception as e:
        log(f"API token creation error: {e}")
        return None


def _update_affiliate_links(referral_url: str):
    """Update affiliate_links.json with the real DigitalOcean referral URL."""
    if not AFFILIATE_FILE.exists():
        log("affiliate_links.json not found — skipping")
        return
    try:
        data = json.loads(AFFILIATE_FILE.read_text())
        for link in data.get("links", []):
            if "digitalocean" in link.get("url", "").lower() or "digitalocean" in link.get("text", "").lower():
                old = link["url"]
                link["url"] = referral_url
                log(f"affiliate_links.json updated: {old} → {referral_url}")
                break
        tmp = AFFILIATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(AFFILIATE_FILE)
    except Exception as e:
        log(f"affiliate_links update failed: {e}")


def _update_golem_env(token: str):
    """Add or replace DIGITALOCEAN_API_TOKEN in golem.env."""
    try:
        lines = GOLEM_ENV.read_text().splitlines() if GOLEM_ENV.exists() else []
        new_lines = [l for l in lines if not l.startswith("DIGITALOCEAN_API_TOKEN=")]
        new_lines.append(f"DIGITALOCEAN_API_TOKEN={token}")
        GOLEM_ENV.write_text("\n".join(new_lines) + "\n")
        log("DIGITALOCEAN_API_TOKEN written to golem.env")
    except Exception as e:
        log(f"golem.env update failed: {e}")


def run_extract():
    """Phase 2 entrypoint: log in and extract referral link + API token."""
    env = load_env()
    email = env.get("GOOGLE_EMAIL") or env.get("GMAIL_ADDRESS", "")
    if not email:
        log("GOOGLE_EMAIL not set — cannot proceed")
        sys.exit(1)
    log(f"starting DO extract for {email}")
    run_extract_with_browser(env)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--signup", action="store_true", help="Phase 1: create account via Google SSO")
    parser.add_argument("--extract", action="store_true", help="Phase 2: extract referral link + API token")
    args = parser.parse_args()

    if args.signup:
        run_signup()
    elif args.extract:
        run_extract()
    else:
        parser.print_help()
