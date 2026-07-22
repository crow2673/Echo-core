#!/usr/bin/env python3
"""tools/validate_secrets.py — what's actually configured vs. what Echo thinks.

Echo's known_gaps.md repeatedly claims credentials are "not set" and bottlenecks
income decisions on them — but many ARE set (and the real blocker is often a
captcha flag, not a missing key). This maps every income-relevant secret to the
stream it unblocks, reports PRESENT / MISSING / BLOCKED, runs a few safe live
checks, and flags stale gaps so Echo stops chasing phantom blockers.

Run: python3 tools/validate_secrets.py
Writes: memory/secrets_status.json + prints a checklist.
"""
import json, urllib.request, urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ENV_FILE = Path.home() / ".config/echo/golem.env"
OUT = BASE / "memory/secrets_status.json"

# secret group -> (required keys, income stream, what it unblocks, captcha flag)
GROUPS = {
    "Reddit outreach":   (["REDDIT_USERNAME", "REDDIT_PASSWORD"], "Fiverr lead-gen", "automated subreddit outreach -> Fiverr leads", None),
    "Fiverr":            (["FIVERR_USERNAME", "FIVERR_PASSWORD"], "Fiverr gigs", "inbox + gig automation", None),
    "Gumroad":           (["GUMROAD_EMAIL", "GUMROAD_PASSWORD"], "Product sales", "list/sell digital products", "GUMROAD_CAPTCHA_BLOCKED"),
    "Dev.to":            (["DEVTO_EMAIL", "DEVTO_PASSWORD"], "Content reach", "publish articles to Dev.to", "DEVTO_CAPTCHA_BLOCKED"),
    "Medium":            (["MEDIUM_TOKEN"], "Content income", "Partner Program pay-per-read", None),
    "Beehiiv newsletter":(["BEEHIIV_API_KEY", "BEEHIIV_PUBLICATION_ID"], "Newsletter", "grow + monetize subscriber list", None),
    "Notion CRM":        (["NOTION_TOKEN", "NOTION_DB_LEADS"], "Pipeline tracking", "leads/income/actions dashboards", None),
    "Alpaca trading":    (["ALPACA_API_KEY", "ALPACA_SECRET_KEY"], "Trading", "live/paper order execution", None),
    "Telegram":          (["TELEGRAM_BOT_TOKEN"], "Notifications", "push alerts + approvals to Andrew", None),
    "Freelancer":        (["FREELANCER_USERNAME", "FREELANCER_PASSWORD"], "Freelance gigs", "bid automation", None),
}


def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _get(url, headers=None, timeout=8):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def live_check(group, env):
    """A few cheap, safe validity pings. Returns (ok|None, note)."""
    try:
        if group == "Alpaca trading":
            base = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
            h = {"APCA-API-KEY-ID": env.get("ALPACA_API_KEY", ""),
                 "APCA-API-SECRET-KEY": env.get("ALPACA_SECRET_KEY", "")}
            s, _ = _get(base + "/v2/account", h)
            return (s == 200, "account reachable" if s == 200 else f"HTTP {s}")
        if group == "Telegram":
            s, b = _get(f"https://api.telegram.org/bot{env.get('TELEGRAM_BOT_TOKEN','')}/getMe")
            ok = json.loads(b).get("ok", False)
            return (ok, "bot token valid" if ok else "token rejected")
        if group == "Notion CRM":
            s, _ = _get("https://api.notion.com/v1/users/me",
                        {"Authorization": f"Bearer {env.get('NOTION_TOKEN','')}",
                         "Notion-Version": "2022-06-28"})
            return (s == 200, "token valid" if s == 200 else f"HTTP {s}")
        if group == "Beehiiv newsletter":
            pid = env.get("BEEHIIV_PUBLICATION_ID", "")
            s, _ = _get(f"https://api.beehiiv.com/v2/publications/{pid}",
                        {"Authorization": f"Bearer {env.get('BEEHIIV_API_KEY','')}"})
            return (s == 200, "api key valid" if s == 200 else f"HTTP {s}")
    except urllib.error.HTTPError as e:
        return (False, f"HTTP {e.code}")
    except Exception as e:
        return (None, f"check skipped ({type(e).__name__})")
    return (None, "no live check")


def main():
    env = load_env()
    report = {}
    print("=" * 64)
    print("  SECRETS STATUS — what's actually configured")
    print("=" * 64)
    for group, (keys, stream, unblocks, captcha) in GROUPS.items():
        present = [k for k in keys if env.get(k)]
        missing = [k for k in keys if not env.get(k)]
        blocked = bool(captcha and env.get(captcha))
        if missing:
            status = "MISSING"
        elif blocked:
            status = "BLOCKED(captcha)"
        else:
            status = "PRESENT"
        ok, note = (None, "")
        if status == "PRESENT":
            ok, note = live_check(group, env)
            if ok is True:
                status = "VALID"
            elif ok is False:
                status = "INVALID"
        report[group] = {"status": status, "stream": stream, "unblocks": unblocks,
                         "missing_keys": missing, "captcha_blocked": blocked, "live_note": note}
        icon = {"VALID": "✅", "PRESENT": "🟢", "MISSING": "❌",
                "BLOCKED(captcha)": "🧱", "INVALID": "⚠️"}.get(status, "•")
        print(f"\n{icon} {group:20} [{status}]  → {stream}")
        print(f"    unblocks: {unblocks}")
        if missing:
            print(f"    MISSING: {', '.join(missing)}")
        if blocked:
            print(f"    captcha flag set ({captcha}) — creds exist but service is captcha-walled")
        if note:
            print(f"    live: {note}")

    # stale-gap detector: creds present but known_gaps says 'not set'
    print("\n" + "=" * 64)
    print("  STALE GAPS — known_gaps.md claims missing, but creds ARE set")
    print("=" * 64)
    gaps = (BASE / "memory/known_gaps.md")
    stale = []
    if gaps.exists():
        text = gaps.read_text().lower()
        for group, (keys, *_rest) in GROUPS.items():
            if all(env.get(k) for k in keys):
                kw = group.split()[0].lower()
                if f"{kw}" in text and ("not set" in text or "missing" in text or "credentials" in text):
                    if kw in ("reddit", "gumroad", "fiverr", "dev.to", "devto"):
                        stale.append(group)
    if stale:
        for g in stale:
            print(f"  ⚠️  {g}: creds present — gap entry is STALE, real blocker is elsewhere (often captcha)")
    else:
        print("  (none detected)")

    OUT.write_text(json.dumps(report, indent=2))
    print(f"\n[written to {OUT}]")


if __name__ == "__main__":
    main()
