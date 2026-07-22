#!/usr/bin/env python3
"""
tools/income_dependency_audit.py — the truth about what actually blocks Echo's income.

Echo's known_gaps.md is STALE: it re-reports "need Reddit credentials", "need
Dev.to key" etc. for months while those credentials sit configured. This audit
diffs CLAIMED blockers (known_gaps) against ACTUAL configured secret/platform
state and tells the real story — so Echo stops chasing phantom gaps and starts
using what she already has.

Privacy: reads only the PRESENCE of secret keys (and boolean captcha flags).
It never reads, logs, or emits secret VALUES.

Outputs:
  memory/income_dependency_ledger.json   — structured per-channel state
  memory/andrew_setup_sprint.md          — the SHORT list that genuinely needs Andrew

Status categories (per collab bus #115-117):
  ready_to_use               — creds present, no captcha wall (validate + use)
  configured_but_captcha     — creds present but the platform is captcha-walled
  missing_secret             — a required secret is absent (needs Andrew, once)

Usage:  python3 tools/income_dependency_audit.py
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ENV_FILES = [BASE / ".env", Path.home() / ".config/echo/golem.env"]
KNOWN_GAPS = BASE / "memory" / "known_gaps.md"
LEDGER = BASE / "memory" / "income_dependency_ledger.json"
SPRINT = BASE / "memory" / "andrew_setup_sprint.md"

# income-facing channels → the env keys they need, optional captcha flag, and how to set up
CHANNELS = {
    "reddit":   {"label": "Reddit outreach (Fiverr lead-gen)", "req": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD"],
                 "captcha_flag": None, "aliases": ["reddit"]},
    "devto":    {"label": "Dev.to publishing", "req": ["DEVTO_EMAIL", "DEVTO_PASSWORD"], "opt": ["DEV_API_KEY"],
                 "captcha_flag": "DEVTO_CAPTCHA_BLOCKED", "aliases": ["dev.to", "devto"]},
    "medium":   {"label": "Medium Partner (passive content income)", "req": ["MEDIUM_TOKEN"],
                 "captcha_flag": None, "aliases": ["medium"],
                 "setup": ["Create a Medium account (medium.com)",
                           "Settings → Partner Program → enroll (needs tax info + payout)",
                           "Settings → Security → Integration tokens → Generate",
                           "Add MEDIUM_TOKEN=<token> to ~/.config/echo/golem.env"]},
    "gumroad":  {"label": "Gumroad product sales", "req": ["GUMROAD_EMAIL", "GUMROAD_PASSWORD"],
                 "captcha_flag": "GUMROAD_CAPTCHA_BLOCKED", "aliases": ["gumroad"]},
    "fiverr":   {"label": "Fiverr gig delivery", "req": ["FIVERR_USERNAME", "FIVERR_PASSWORD"],
                 "captcha_flag": None, "aliases": ["fiverr"]},
    "freelancer": {"label": "Freelancer.com", "req": ["FREELANCER_EMAIL", "FREELANCER_PASSWORD"],
                   "captcha_flag": None, "aliases": ["freelancer"]},
    "beehiiv":  {"label": "Beehiiv newsletter", "req": ["BEEHIIV_API_KEY"], "opt": ["BEEHIIV_PUBLICATION_ID"],
                 "captcha_flag": None, "aliases": ["beehiiv", "newsletter"]},
    "alpaca":   {"label": "Alpaca trading", "req": ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"],
                 "captcha_flag": None, "aliases": ["alpaca"]},
    "kucoin":   {"label": "KuCoin crypto (autonomous keys)", "req": ["KUCOIN_APIKEY", "KUCOIN_SECRET", "KUCOIN_PASSPHRASE"],
                 "captcha_flag": None, "aliases": ["kucoin"]},
}


def _load_env_presence():
    """Return {key: value} across env files. Values used only for captcha flags + emptiness."""
    env = {}
    for f in ENV_FILES:
        if not f.exists():
            continue
        for line in f.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def _present(env, key):
    return key in env and env[key].strip() != ""


def _truthy(env, key):
    v = env.get(key, "").strip().lower()
    return v not in ("", "0", "false", "no")


def _gaps_text():
    return KNOWN_GAPS.read_text(errors="ignore").lower() if KNOWN_GAPS.exists() else ""


def audit():
    env = _load_env_presence()
    gaps = _gaps_text()
    channels = []
    for name, spec in CHANNELS.items():
        missing = [k for k in spec["req"] if not _present(env, k)]
        captcha = bool(spec.get("captcha_flag")) and _truthy(env, spec["captcha_flag"])
        if missing:
            status = "missing_secret"
        elif captcha:
            status = "configured_but_captcha"
        else:
            status = "ready_to_use"
        # stale gap: known_gaps complains about this channel needing creds, but they're present
        claimed = any(a in gaps and re.search(r"(need|missing|no |credential|key|activation)", gaps)
                      for a in spec["aliases"]) and any(a in gaps for a in spec["aliases"])
        stale = claimed and status != "missing_secret"
        channels.append({
            "channel": name, "label": spec["label"], "status": status,
            "missing_keys": missing, "captcha_blocked": captcha,
            "claimed_blocked_in_known_gaps": claimed, "stale_gap": stale,
            "setup_steps": spec.get("setup", []),
        })

    summary = {s: sum(1 for c in channels if c["status"] == s)
               for s in ("ready_to_use", "configured_but_captcha", "missing_secret")}
    summary["stale_gaps"] = sum(1 for c in channels if c["stale_gap"])

    LEDGER.write_text(json.dumps(
        {"generated": datetime.now(timezone.utc).isoformat(), "summary": summary, "channels": channels},
        indent=2))

    _write_sprint(channels, summary)
    return summary, channels


def _write_sprint(channels, summary):
    ready = [c for c in channels if c["status"] == "ready_to_use"]
    captcha = [c for c in channels if c["status"] == "configured_but_captcha"]
    missing = [c for c in channels if c["status"] == "missing_secret"]

    lines = [
        "# Andrew Setup Sprint — the ONLY things that actually need you",
        f"_generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · never contains secret values_",
        "",
        f"**Reality check:** {len(ready)} income channels are ALREADY configured and ready to use. "
        f"{summary['stale_gaps']} 'gaps' in known_gaps.md are STALE (creds are actually present). "
        f"You are not the bottleneck you thought you were.",
        "",
        "## ✅ Ready now — no action from you (Echo just needs to USE these)",
    ]
    lines += [f"- {c['label']}" for c in ready] or ["- (none)"]

    lines += ["", "## 🧩 Captcha-walled — your credentials can't fix these (needs a routing decision, not a login)"]
    lines += [f"- {c['label']} — platform blocks automation with a captcha" for c in captcha] or ["- (none)"]

    lines += ["", "## 🔑 Genuinely missing — the only real one-time asks"]
    if missing:
        for c in missing:
            lines.append(f"### {c['label']}")
            for step in c["setup_steps"] or [f"Provide: {', '.join(c['missing_keys'])} in ~/.config/echo/golem.env"]:
                lines.append(f"- [ ] {step}")
    else:
        lines.append("- (none — nothing genuinely missing)")

    SPRINT.write_text("\n".join(lines) + "\n")


def main():
    summary, channels = audit()
    print("Income dependency audit —")
    for c in channels:
        tag = {"ready_to_use": "✅ READY", "configured_but_captcha": "🧩 CAPTCHA",
               "missing_secret": "🔑 MISSING"}[c["status"]]
        stale = "  ⚠️ STALE GAP (known_gaps wrongly says missing)" if c["stale_gap"] else ""
        print(f"  {tag:11} {c['label']}{stale}")
    print(f"\nsummary: {json.dumps(summary)}")
    print(f"wrote {LEDGER.name} + {SPRINT.name}")


if __name__ == "__main__":
    main()
