#!/usr/bin/env python3
"""
echo_screen_watcher.py
======================
Echo's eyes. Takes periodic screenshots, reads what's on screen,
and sends context capsules to Echo so she knows what Andrew is working on.

Usage:
    python3 echo_screen_watcher.py              # runs continuously
    python3 echo_screen_watcher.py --once       # single snapshot
    python3 echo_screen_watcher.py --interval 120  # every 2 minutes

Echo receives capsules like:
    "Andrew is currently working on: [terminal, code editor, browser tab X]"
"""

import os
import sys
import json
import time
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Force working directory to Echo
os.chdir(Path(__file__).resolve().parent)

INTERVAL_DEFAULT = 60  # seconds between screenshots
SCREENSHOT_PATH = "/tmp/echo_screen.png"
MEMORY_FILE = Path("echo_memory.json")
LOCK_FILE = Path("echo_memory.lock")


# ── SCREENSHOT ────────────────────────────────────────────────────────────────

def take_screenshot() -> bool:
    """Take a screenshot using scrot or gnome-screenshot."""
    # Try scrot first (faster, no GUI needed)
    try:
        result = subprocess.run(
            ["scrot", "-z", SCREENSHOT_PATH],
            capture_output=True, timeout=10
        )
        if result.returncode == 0 and Path(SCREENSHOT_PATH).exists():
            return True
    except Exception:
        pass

    # Fallback to gnome-screenshot
    try:
        result = subprocess.run(
            ["gnome-screenshot", "-f", SCREENSHOT_PATH],
            capture_output=True, timeout=10
        )
        if result.returncode == 0 and Path(SCREENSHOT_PATH).exists():
            return True
    except Exception:
        pass

    # Fallback to mss
    try:
        import mss
        with mss.mss() as sct:
            sct.shot(output=SCREENSHOT_PATH)
        return Path(SCREENSHOT_PATH).exists()
    except Exception:
        pass

    return False


# ── OCR ───────────────────────────────────────────────────────────────────────

def read_screen_text() -> str:
    """OCR the screenshot and return cleaned text."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(SCREENSHOT_PATH)
        # Resize for faster OCR
        img = img.resize((img.width // 2, img.height // 2))
        text = pytesseract.image_to_string(img, config='--psm 11')
        # Clean up
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return "\n".join(lines[:50])  # max 50 lines
    except Exception as e:
        return f"(OCR failed: {e})"


# ── WINDOW DETECTION ─────────────────────────────────────────────────────────

def get_active_windows() -> list:
    """Get list of open window titles."""
    try:
        result = subprocess.run(
            ["wmctrl", "-l"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            windows = []
            for line in result.stdout.splitlines():
                parts = line.split(None, 3)
                if len(parts) >= 4:
                    title = parts[3].strip()
                    if title and title != "echo-X570-Taichi":
                        windows.append(title)
            return windows[:8]  # top 8 windows
    except Exception:
        pass

    # Fallback: check process names
    try:
        result = subprocess.run(
            ["ps", "aux", "--no-header"],
            capture_output=True, text=True
        )
        procs = []
        for line in result.stdout.splitlines():
            for app in ["firefox", "chrome", "code", "terminal", "ptyxis",
                       "nautilus", "gedit", "vlc", "spotify", "telegram"]:
                if app in line.lower() and app not in procs:
                    procs.append(app)
        return procs
    except Exception:
        return []


# ── CONTEXT BUILDER ───────────────────────────────────────────────────────────

def build_screen_context(windows: list, ocr_text: str) -> str:
    """Build a concise summary of what's on screen."""
    parts = []

    if windows:
        parts.append(f"Open windows: {', '.join(windows[:5])}")

    # Extract meaningful OCR snippets
    if ocr_text and "(OCR failed" not in ocr_text:
        # Look for terminal commands, file names, URLs
        meaningful = []
        for line in ocr_text.splitlines():
            line = line.strip()
            if len(line) > 10 and len(line) < 200:
                # Skip lines that are mostly symbols
                alpha_ratio = sum(c.isalpha() for c in line) / max(len(line), 1)
                if alpha_ratio > 0.3:
                    meaningful.append(line)
            if len(meaningful) >= 10:
                break

        if meaningful:
            parts.append(f"Screen content: {' | '.join(meaningful[:5])}")

    return " — ".join(parts) if parts else "Screen content unclear"


# ── CAPSULE SENDER ────────────────────────────────────────────────────────────

def _file_lock_acquire(timeout=5.0) -> bool:
    start = time.time()
    while True:
        try:
            fd = LOCK_FILE.open("x")
            fd.write(str(time.time()))
            fd.flush()
            fd.close()
            return True
        except FileExistsError:
            if time.time() - start > timeout:
                return False
            time.sleep(0.05)


def _file_lock_release():
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


def send_screen_context(context: str):
    """Send screen context as an event capsule to Echo."""
    ts = datetime.now(timezone.utc).isoformat()
    capsule = {
        "capsule_id": f"SCREEN:{ts}",
        "type": "event",
        "subtype": "screen_context",
        "from": "screen_watcher",
        "text": f"[Screen Context] {context}",
        "status": "new",
        "created_at": ts,
    }

    if not _file_lock_acquire():
        print("[screen] Could not acquire lock, skipping")
        return

    try:
        data = []
        if MEMORY_FILE.exists() and MEMORY_FILE.stat().st_size > 0:
            try:
                data = json.loads(MEMORY_FILE.read_text())
            except Exception:
                data = []
        data.append(capsule)
        tmp = MEMORY_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        tmp.replace(MEMORY_FILE)
        print(f"[screen] Sent context: {context[:80]}...")
    finally:
        _file_lock_release()


# Also store in semantic memory for long-term context
def store_in_memory(context: str):
    """Store screen context in semantic memory."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from echo_memory_sqlite import get_memory
        m = get_memory()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        m.add(
            f"At {ts}, Andrew was working on: {context}",
            {"type": "screen_context", "priority": "low"}
        )
    except Exception as e:
        print(f"[screen] Memory store failed: {e}")


# ── MAIN LOOP ─────────────────────────────────────────────────────────────────

def snapshot():
    """Take one snapshot and send to Echo."""
    print("[screen] Taking screenshot...")
    if not take_screenshot():
        print("[screen] Screenshot failed")
        return

    windows = get_active_windows()
    ocr_text = read_screen_text()
    context = build_screen_context(windows, ocr_text)

    print(f"[screen] Context: {context[:100]}")
    send_screen_context(context)

    # Store in long-term memory every snapshot
    store_in_memory(context)
    # Log to unified event ledger
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from core.event_ledger import log_event
        log_event("screen", "screen_watcher", context[:300])
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Echo Screen Watcher")
    parser.add_argument("--once", action="store_true", help="Single snapshot then exit")
    parser.add_argument("--interval", type=int, default=INTERVAL_DEFAULT,
                        help=f"Seconds between snapshots (default: {INTERVAL_DEFAULT})")
    args = parser.parse_args()

    print(f"[screen] Echo Screen Watcher starting (interval: {args.interval}s)")

    if args.once:
        snapshot()
        return

    # Install wmctrl if missing (for window titles)
    subprocess.run(["sudo", "apt", "install", "-y", "wmctrl"],
                   capture_output=True)

    while True:
        try:
            snapshot()
        except Exception as e:
            print(f"[screen] Error: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
