#!/usr/bin/env python3
"""
core/google_sso.py — Shared Google SSO login helper for Playwright scripts.

Handles the Google accounts.google.com auth flow: email → Next → password → Next.
Also handles the "choose an account" picker if a prior session exists.
Returns True on success, False on failure.

Usage:
    from core.google_sso import google_login
    ok = google_login(page, email, password)
"""

import time
import logging
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/google_sso.log"
LOG.parent.mkdir(exist_ok=True)
logging.basicConfig(filename=LOG, level=logging.INFO, format="%(asctime)s %(message)s")


def _log(msg):
    print(f"[google_sso] {msg}", flush=True)
    logging.info(msg)


def _wait_visible(page, selectors, timeout_each=4000):
    """Return first locator that becomes visible, or None."""
    for sel in selectors:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=timeout_each)
            return el
        except Exception:
            continue
    return None


def _handle_account_chooser(page, email):
    """
    If Google shows 'Choose an account', click the matching account.
    Returns True if handled, False if not on that screen.
    """
    try:
        chooser = page.locator('[data-identifier], [data-email], li[jsname]').first
        chooser.wait_for(state="visible", timeout=3000)
    except Exception:
        return False

    # Try to click the matching email tile
    email_lower = email.lower()
    selectors = [
        f'[data-identifier="{email}"]',
        f'[data-email="{email}"]',
        f'div[data-identifier*="{email_lower.split("@")[0]}"]',
    ]
    for sel in selectors:
        try:
            page.click(sel, timeout=3000)
            _log(f"clicked account tile for {email}")
            time.sleep(1)
            return True
        except Exception:
            continue

    # If tile not found, click "Use another account" and fall through to email entry
    try:
        page.click('li[jsname="D1NHk"], [data-action="addaccount"]', timeout=3000)
        time.sleep(1)
        _log("clicked 'use another account'")
    except Exception:
        pass
    return False


def google_login(page, email: str, password: str, timeout: int = 30000) -> bool:
    """
    Complete a Google OAuth login on the current page/popup.
    Assumes the page is already at an accounts.google.com URL.
    Returns True on success.
    """
    _log(f"starting Google login for {email}")
    time.sleep(2)

    # ── Step 1: Account chooser or email entry ─────────────────────────────
    if not _handle_account_chooser(page, email):
        email_field = _wait_visible(page, [
            'input[type="email"]',
            'input[id="identifierId"]',
            'input[name="identifier"]',
        ])
        if not email_field:
            _log("no email field found on Google login page")
            return False
        email_field.fill(email)
        _log("filled email")

        next_btn = _wait_visible(page, ['#identifierNext', 'button[jsname="LgbsSe"]', 'div[jsname="VlcLAe"] button'])
        if next_btn:
            next_btn.click()
        else:
            page.keyboard.press("Enter")
        time.sleep(2)

    # ── Step 2: Password ───────────────────────────────────────────────────
    pwd_field = _wait_visible(page, [
        'input[type="password"]',
        'input[name="password"]',
        'input[name="Passwd"]',
        'input[id="password"]',
    ], timeout_each=8000)
    if not pwd_field:
        _log("no password field found")
        return False
    pwd_field.fill(password)
    _log("filled password")

    pwd_next = _wait_visible(page, ['#passwordNext', 'button[jsname="LgbsSe"]', 'div[jsname="M9Bg4d"] button'])
    if pwd_next:
        pwd_next.click()
    else:
        page.keyboard.press("Enter")

    time.sleep(3)

    # ── Step 3: Post-login check ───────────────────────────────────────────
    # We're done if we've been redirected away from accounts.google.com
    if "accounts.google.com" not in page.url:
        _log("Google login succeeded — redirected to target site")
        return True

    # Still on Google — might be a 2FA / verify step
    current_url = page.url
    _log(f"still on Google after password ({current_url[:80]}) — possible 2FA")
    # Wait a bit longer in case of redirect
    try:
        page.wait_for_url(lambda u: "accounts.google.com" not in u, timeout=timeout)
        _log("redirected after wait — login successful")
        return True
    except Exception:
        _log("timed out waiting for redirect — login may require 2FA")
        return False


def handle_google_sso_button(page, email: str, password: str,
                              button_selectors: list = None) -> bool:
    """
    Click a 'Continue with Google' button on the current page, handle any
    popup or redirect, complete the Google login, and return True on success.

    button_selectors: CSS selectors to try for the Google login button.
    """
    if button_selectors is None:
        button_selectors = [
            'a[href*="google"][href*="login"], a[href*="google"][href*="auth"]',
            'button:has-text("Continue with Google")',
            'button:has-text("Sign in with Google")',
            'button:has-text("Log in with Google")',
            '[aria-label*="Google"]',
            'div[class*="google"] button, button[class*="google"]',
            'a[class*="google"]',
        ]

    google_btn = None
    for sel in button_selectors:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=3000)
            google_btn = el
            _log(f"found Google button via: {sel}")
            break
        except Exception:
            continue

    if not google_btn:
        _log("no 'Continue with Google' button found")
        return False

    # Google auth may open in a popup or redirect in-page
    with page.expect_popup(timeout=5000) as popup_info:
        try:
            google_btn.click()
            popup_page = popup_info.value
            _log("Google auth opened in popup")
            popup_page.wait_for_load_state("domcontentloaded")
            result = google_login(popup_page, email, password)
            if result:
                popup_page.wait_for_close(timeout=10000)
            return result
        except Exception:
            # No popup — it's a redirect flow
            pass

    # Redirect flow: just clicked the button, now we're navigating
    _log("Google auth is a redirect flow")
    try:
        page.wait_for_url("**/accounts.google.com/**", timeout=10000)
        return google_login(page, email, password)
    except Exception:
        pass

    # If we're already past Google (fast redirect), check if logged in
    time.sleep(2)
    if "accounts.google.com" not in page.url:
        _log("already past Google login (existing session?)")
        return True

    _log("could not complete Google SSO flow")
    return False
