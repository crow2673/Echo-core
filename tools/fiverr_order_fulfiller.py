#!/usr/bin/env python3
"""
tools/fiverr_order_fulfiller.py — Detects new Fiverr orders, generates Python deliverables,
uploads them, and sends the delivery message. Fully autonomous order fulfillment.

Flow:
  1. Login to Fiverr via Playwright
  2. Scan /orders for in-progress orders not yet fulfilled by Echo
  3. Read order requirements (buyer's answers)
  4. Generate Python script deliverable using qwen2.5:32b
  5. Upload file + delivery message via Playwright
  6. Notify Andrew with what was delivered

Runs every 30 min via echo-fiverr-fulfiller.timer.
"""
import json
import sys
import time
import logging
import tempfile
import os
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

LOG = BASE / "logs/fiverr_fulfiller.log"
FULFILLED_FILE = BASE / "memory/fiverr_orders_fulfilled.json"
COOKIES_FILE = Path.home() / ".config/echo/fiverr_cookies.json"

logging.basicConfig(filename=str(LOG), level=logging.INFO, format="%(asctime)s %(message)s")

DELIVERY_SYSTEM_PROMPT = """You are a Python expert building automation tools for clients on Fiverr.
The client paid for a "local AI automation system in Python that runs on their hardware."

Write a complete, working Python 3 script that fulfills the client's requirement.

RULES:
- Start with #!/usr/bin/env python3 and a clear docstring explaining what the script does
- All file writes use atomic .tmp rename pattern
- Every external call wrapped in try/except with useful error messages
- Logging to a .log file using Python's logging module
- Clear CLI argument handling with argparse if needed
- A README-style comment block at the top after the docstring explaining how to run it
- Works on Ubuntu/Linux, requires only standard library + commonly available packages
- if __name__ == "__main__": block at the bottom
- No hardcoded credentials — read from env vars or a config file

Output ONLY the Python code. No markdown, no explanation, no code fences."""


def log(msg):
    print(f"[fiverr_fulfiller] {msg}", flush=True)
    logging.info(msg)


def _get_env():
    env = {}
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _load_fulfilled():
    if FULFILLED_FILE.exists():
        try:
            return json.loads(FULFILLED_FILE.read_text())
        except Exception:
            pass
    return []


def _save_fulfilled(fulfilled):
    tmp = FULFILLED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(fulfilled, indent=2, default=str))
    tmp.rename(FULFILLED_FILE)


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
    page.goto("https://www.fiverr.com", wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    logged_in = bool(
        page.query_selector("[data-testid='header-profile']") or
        page.query_selector("[class*='profile-image']") or
        page.query_selector("a[href*='/inbox']")
    )
    if logged_in:
        log("session valid")
        return True

    log("logging in...")
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
            log(f"Google SSO failed: {e}")

    log("login failed")
    return False


def generate_deliverable(requirements: str, order_title: str) -> tuple[str, str]:
    """Generate Python script for the order. Returns (code, filename)."""
    from core.providers.router import call_ollama
    import re

    prompt = (
        f"Client's order title: {order_title}\n\n"
        f"Client's requirements:\n{requirements}\n\n"
        f"Build a complete Python automation script that fulfills this requirement exactly."
    )

    log(f"generating deliverable for: {order_title[:60]}")
    code = call_ollama(prompt, model="qwen2.5:32b", timeout=600, system_prompt=DELIVERY_SYSTEM_PROMPT)

    if not code or len(code.strip()) < 100:
        raise ValueError(f"LLM returned empty/short code ({len(code or '')} chars)")

    # Strip markdown fences if model added them
    code = re.sub(r"^```python\s*", "", code, flags=re.MULTILINE)
    code = re.sub(r"^```\s*$", "", code, flags=re.MULTILINE)
    code = code.strip()

    if not code.startswith("#"):
        code = f"#!/usr/bin/env python3\n{code}"

    # Make a safe filename from the order title
    safe = re.sub(r"[^a-z0-9]", "_", order_title.lower())[:40].strip("_")
    filename = f"{safe}_automation.py"

    return code, filename


def read_order_requirements(page, order_url: str) -> tuple[str, str]:
    """
    Navigate to an order page and extract requirements and title.
    Returns (requirements_text, order_title).
    """
    page.goto(order_url, wait_until="networkidle", timeout=30000)
    time.sleep(3)

    # Get order title
    title = ""
    for sel in ["h1", "[class*='order-title']", "[class*='gig-title']", "h2"]:
        el = page.query_selector(sel)
        if el:
            title = el.inner_text().strip()
            if title:
                break

    # Get requirements — buyer's answers to the gig questionnaire
    req_text = ""
    req_selectors = [
        "[class*='requirements']",
        "[class*='buyer-answers']",
        "[class*='order-requirements']",
        "[class*='requirements-section']",
        "[data-testid*='requirements']",
    ]
    for sel in req_selectors:
        el = page.query_selector(sel)
        if el:
            req_text = el.inner_text().strip()
            if req_text:
                break

    # Fallback: try the requirements tab
    if not req_text:
        try:
            req_tab = page.query_selector("a[href*='requirements'], button[class*='requirements']")
            if req_tab:
                req_tab.click()
                time.sleep(2)
                for sel in req_selectors:
                    el = page.query_selector(sel)
                    if el:
                        req_text = el.inner_text().strip()
                        if req_text:
                            break
        except Exception:
            pass

    # Final fallback: grab all visible text from the order page
    if not req_text:
        body = page.query_selector("main") or page.query_selector("body")
        req_text = body.inner_text()[:2000] if body else ""

    return req_text, title


def deliver_order(page, order_url: str, code: str, filename: str, order_title: str) -> bool:
    """Upload the deliverable and submit the delivery."""
    page.goto(order_url, wait_until="networkidle", timeout=30000)
    time.sleep(3)

    # Find and click "Deliver Work" button
    deliver_selectors = [
        "button[class*='deliver']",
        "a[class*='deliver']",
        "button[data-testid*='deliver']",
        "[class*='deliver-work']",
        "button:has-text('Deliver')",
        "a:has-text('Deliver')",
    ]
    clicked = False
    for sel in deliver_selectors:
        try:
            btn = page.locator(sel).first
            btn.wait_for(state="visible", timeout=3000)
            btn.click()
            clicked = True
            log(f"clicked deliver button using {sel}")
            break
        except Exception:
            continue

    if not clicked:
        log("could not find 'Deliver Work' button")
        return False

    time.sleep(2)

    # Write code to a temp file and upload it
    with tempfile.NamedTemporaryFile(suffix=f"_{filename}", mode="w", delete=False) as tf:
        tf.write(code)
        tmp_path = tf.name

    try:
        upload_selectors = [
            "input[type='file']",
            "[class*='upload'] input",
            "[data-testid*='upload'] input",
        ]
        uploaded = False
        for sel in upload_selectors:
            try:
                file_input = page.locator(sel).first
                file_input.set_input_files(tmp_path)
                uploaded = True
                log(f"uploaded file using {sel}")
                break
            except Exception:
                continue

        if not uploaded:
            log("could not find file upload input")
            return False

        time.sleep(3)

        # Write delivery message
        delivery_msg = (
            f"Hi! I've completed your automation script '{filename}'.\n\n"
            f"The script is fully documented and ready to run on your machine. "
            f"It follows best practices: error handling, logging to a .log file, "
            f"and atomic file writes to prevent data corruption.\n\n"
            f"To run it:\n"
            f"1. Make sure Python 3 is installed\n"
            f"2. Install any dependencies listed at the top of the file\n"
            f"3. Run: python3 {filename}\n\n"
            f"Let me know if you need any adjustments or have questions!"
        )

        msg_selectors = [
            "textarea[placeholder*='delivery' i]",
            "textarea[placeholder*='message' i]",
            "textarea[class*='delivery']",
            "div[contenteditable='true']",
            "textarea",
        ]
        for sel in msg_selectors:
            try:
                el = page.locator(sel).last
                el.wait_for(state="visible", timeout=3000)
                el.fill(delivery_msg)
                break
            except Exception:
                continue

        time.sleep(1)

        # Submit delivery
        submit_selectors = [
            "button[type='submit']",
            "button[class*='submit-delivery']",
            "button:has-text('Submit')",
            "button:has-text('Deliver')",
        ]
        for sel in submit_selectors:
            try:
                btn = page.locator(sel).last
                btn.wait_for(state="visible", timeout=3000)
                btn.click()
                log("delivery submitted")
                time.sleep(3)
                return True
            except Exception:
                continue

        log("could not find submit button")
        return False

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def scan_orders(page) -> list[dict]:
    """Scan the orders page for in-progress orders."""
    log("scanning orders page...")
    orders = []

    for url in [
        "https://www.fiverr.com/orders?state=in-progress",
        "https://www.fiverr.com/orders",
        "https://www.fiverr.com/seller_dashboard",
    ]:
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(3)

            order_selectors = [
                "[class*='order-item']",
                "[class*='order-row']",
                "[data-testid*='order']",
                "tr[class*='order']",
                "li[class*='order']",
            ]
            for sel in order_selectors:
                els = page.query_selector_all(sel)
                if els:
                    log(f"found {len(els)} orders at {url}")
                    for el in els:
                        link = el.query_selector("a[href*='/orders/']")
                        if not link:
                            continue
                        href = link.get_attribute("href") or ""
                        if "/orders/" not in href:
                            continue
                        order_url = f"https://www.fiverr.com{href}" if href.startswith("/") else href
                        order_id = [p for p in href.split("/") if p][-1]
                        title_el = el.query_selector("[class*='title'], h3, h4, p")
                        title = title_el.inner_text().strip()[:100] if title_el else order_id
                        orders.append({"order_id": order_id, "url": order_url, "title": title})
                    if orders:
                        return orders
        except Exception as e:
            log(f"error scanning {url}: {e}")

    return orders


def run():
    log("starting")
    env = _get_env()

    if not (env.get("GOOGLE_PASSWORD") or env.get("FIVERR_PASSWORD")):
        log("no login credentials — exiting")
        return

    fulfilled = _load_fulfilled()
    fulfilled_ids = {f["order_id"] for f in fulfilled}

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
            orders = scan_orders(page)
            log(f"found {len(orders)} total orders, {len(fulfilled_ids)} already fulfilled")

            for order in orders:
                order_id = order["order_id"]
                if order_id in fulfilled_ids:
                    continue

                log(f"processing order {order_id}: {order['title'][:50]}")

                try:
                    requirements, title = read_order_requirements(page, order["url"])
                    if not requirements.strip():
                        log(f"order {order_id}: no requirements found — skipping")
                        continue

                    effective_title = title or order["title"]
                    code, filename = generate_deliverable(requirements[:3000], effective_title)

                    import py_compile, tempfile as _tf
                    with _tf.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as check_f:
                        check_f.write(code)
                        check_path = check_f.name
                    try:
                        py_compile.compile(check_path, doraise=True)
                        syntax_ok = True
                    except py_compile.PyCompileError as e:
                        log(f"order {order_id}: generated code has syntax error: {e}")
                        syntax_ok = False
                    finally:
                        try:
                            os.unlink(check_path)
                        except Exception:
                            pass

                    if not syntax_ok:
                        continue

                    delivered = deliver_order(page, order["url"], code, filename, effective_title)

                    record = {
                        "order_id": order_id,
                        "title": effective_title[:100],
                        "filename": filename,
                        "delivered": delivered,
                        "fulfilled_at": datetime.now().isoformat(),
                    }
                    fulfilled.append(record)
                    fulfilled_ids.add(order_id)
                    _save_fulfilled(fulfilled)

                    try:
                        from core.notifier import notify
                        status = "delivered" if delivered else "attempted (check manually)"
                        notify(
                            "Fiverr Order Fulfilled" if delivered else "Fiverr Order — check needed",
                            f"Order: {effective_title[:80]}\nFile: {filename}\nStatus: {status}",
                            urgent=not delivered,
                        )
                    except Exception:
                        pass

                    log(f"order {order_id}: {'DELIVERED' if delivered else 'FAILED'}")
                    time.sleep(5)

                except Exception as e:
                    log(f"order {order_id} error: {e}")
                    try:
                        from core.notifier import notify
                        notify(
                            "Fiverr Order — manual delivery needed",
                            f"Order: {order.get('title','?')[:80]}\nError: {str(e)[:200]}",
                            urgent=True,
                        )
                    except Exception:
                        pass
                    continue

        except Exception as e:
            log(f"run error: {e}")
        finally:
            browser.close()

    log("done")


if __name__ == "__main__":
    run()
