#!/usr/bin/env python3
"""
tools/newsletter_composer.py — Echo writes and sends a weekly automation newsletter.

"Build With Echo" — weekly digest of automation scripts, AI tools, and indie hacker tips.
Sent via Beehiiv API (free tier: unlimited sends, no credit card).

Free → paid at $7/mo once 200 subscribers.
100 paid subscribers = $700/mo. 500 = $3,500/mo.

Setup: add BEEHIIV_API_KEY + BEEHIIV_PUBLICATION_ID to ~/.config/echo/golem.env
Beehiiv API: https://developers.beehiiv.com/
"""
import json
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs" / "newsletter.log"
LOG.parent.mkdir(exist_ok=True)
NEWSLETTER_LOG = BASE / "memory" / "newsletter_issues.json"

BEEHIIV_API = "https://api.beehiiv.com/v2"

NEWSLETTER_NAME = "Build With Echo"
NEWSLETTER_TAGLINE = "Weekly automation scripts and AI workflows from an AI that actually runs them."


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [newsletter] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def load_env():
    env = {}
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()
    return env


def load_issues():
    if NEWSLETTER_LOG.exists():
        try:
            return json.loads(NEWSLETTER_LOG.read_text())
        except Exception:
            pass
    return {"issues": []}


def save_issues(data):
    tmp = NEWSLETTER_LOG.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(NEWSLETTER_LOG)


def _gather_content() -> dict:
    """Pull this week's content from Echo's memory."""
    content = {}

    # Recent builds
    builds_reg = BASE / "builds" / "registry.json"
    if builds_reg.exists():
        try:
            reg = json.loads(builds_reg.read_text())
            deployed = [(k, v) for k, v in reg.items() if v.get("status") == "deployed"]
            content["recent_builds"] = deployed[-3:] if deployed else []
        except Exception:
            content["recent_builds"] = []

    # Top leads (market pulse)
    leads_file = BASE / "memory" / "demand_leads.json"
    if leads_file.exists():
        try:
            leads = json.loads(leads_file.read_text())
            top = sorted(leads, key=lambda l: l.get("score", 0), reverse=True)[:5]
            content["top_leads"] = top
        except Exception:
            content["top_leads"] = []

    # Published articles
    content_dir = BASE / "content"
    articles = []
    if content_dir.exists():
        for f in sorted(content_dir.glob("*.md"))[-3:]:
            try:
                text = f.read_text()
                title = text.splitlines()[0].lstrip('#').strip()
                articles.append({"title": title, "file": f.name})
            except Exception:
                pass
    content["articles"] = articles

    return content


def _compose_issue(issue_number: int, content: dict) -> str:
    """Write the newsletter issue as HTML."""
    week = datetime.now().strftime("%B %d, %Y")
    builds = content.get("recent_builds", [])
    leads = content.get("top_leads", [])
    articles = content.get("articles", [])

    html = f"""
<h2>Issue #{issue_number} — {week}</h2>
<p style="color:#666;font-size:14px">{NEWSLETTER_TAGLINE}</p>
<hr>

<h3>🔧 What I Built This Week</h3>
"""
    if builds:
        html += "<ul>"
        for name, meta in builds:
            desc = meta.get("description", name)[:100]
            html += f"<li><strong>{name}</strong> — {desc}</li>"
        html += "</ul>"
    else:
        html += "<p>Working on new automation tools — stay tuned.</p>"

    if leads:
        html += "<h3>📡 What the Market Wants Right Now</h3>"
        html += "<p style='color:#666;font-size:13px'>Top requests spotted on Reddit this week:</p><ul>"
        for lead in leads[:4]:
            html += f"<li>{lead.get('title', '')[:100]}</li>"
        html += "</ul>"

    if articles:
        html += "<h3>📝 Latest Articles</h3><ul>"
        for a in articles:
            html += f"<li>{a['title']}</li>"
        html += "</ul>"

    html += """
<hr>
<h3>💡 Tip of the Week</h3>
<p>If you're doing anything repetitive more than 3 times, it can probably be automated.
The cost of automation has dropped to near-zero. A Python script costs nothing to run.
The only question is whether you spend 2 hours writing it once, or 2 hours/week doing it manually forever.</p>

<hr>
<p style="color:#999;font-size:12px">
Built by Echo — an autonomous AI running 24/7 in Mena, Arkansas.<br>
You're getting this because you asked for practical automation content.
</p>
"""
    return html


def _send_via_beehiiv(api_key: str, pub_id: str, subject: str, html: str) -> dict | None:
    """Create a draft post on Beehiiv."""
    payload = json.dumps({
        "subject": subject,
        "subtitle": NEWSLETTER_TAGLINE,
        "content": {"html": html},
        "status": "draft",  # draft until Echo (or Andrew) reviews
        "send_at": None,
    }).encode()

    req = urllib.request.Request(
        f"{BEEHIIV_API}/publications/{pub_id}/posts",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        log(f"Beehiiv request failed: {e}")
        return None


def run() -> dict:
    env = load_env()
    api_key = env.get("BEEHIIV_API_KEY", "")
    pub_id = env.get("BEEHIIV_PUBLICATION_ID", "")

    if not api_key or not pub_id:
        log("BEEHIIV_API_KEY or BEEHIIV_PUBLICATION_ID not set — skipping")
        log("Get your free Beehiiv account at beehiiv.com, add keys to ~/.config/echo/golem.env")
        return {"status": "no_key"}

    data = load_issues()
    issue_number = len(data["issues"]) + 1

    # Only send weekly
    if data["issues"]:
        last = data["issues"][-1]
        try:
            from datetime import timedelta
            last_dt = datetime.fromisoformat(last["sent_at"])
            if (datetime.now() - last_dt).days < 7:
                log(f"Last issue sent {(datetime.now() - last_dt).days}d ago — not time yet")
                return {"status": "too_soon"}
        except Exception:
            pass

    content = _gather_content()
    html = _compose_issue(issue_number, content)
    week = datetime.now().strftime("%B %d")
    subject = f"#{issue_number}: What I automated this week ({week})"

    log(f"composing issue #{issue_number}: {subject}")
    result = _send_via_beehiiv(api_key, pub_id, subject, html)

    if result:
        data["issues"].append({
            "number": issue_number,
            "subject": subject,
            "sent_at": datetime.now().isoformat(),
            "post_id": result.get("data", {}).get("id", ""),
        })
        save_issues(data)
        log(f"issue #{issue_number} created as draft on Beehiiv")
        return {"status": "ok", "issue": issue_number, "subject": subject}
    else:
        return {"status": "failed"}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
