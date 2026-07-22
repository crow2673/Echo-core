#!/usr/bin/env python3
"""
tools/affiliate_injector.py — Echo earns passive income from her own content.

Scans published Dev.to articles and injects affiliate links for tools mentioned.
Runs after every article publish. Truly passive — articles earn while Echo sleeps.

Setup: add affiliate codes to ~/.config/echo/golem.env:
  AFFILIATE_N8N=your_code          # n8n.io/affiliate
  AFFILIATE_NOTION=your_code       # notion.so/affiliates
  AFFILIATE_AIRTABLE=your_code     # airtable.com/partners
  AFFILIATE_ZAPIER=your_code       # zapier.com/partners
  DEVTO_API_KEY=your_key           # needed to update articles
"""
import json
import re
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs" / "affiliate_injector.log"
LOG.parent.mkdir(exist_ok=True)
AFFILIATE_LOG = BASE / "memory" / "affiliate_injections.json"

DEVTO_API = "https://dev.to/api"

# Tool → (display text, URL template, env key)
AFFILIATE_RULES = [
    ("n8n",    "n8n",    "https://n8n.io/?ref={code}",                  "AFFILIATE_N8N"),
    ("notion", "Notion", "https://www.notion.so/?r={code}",             "AFFILIATE_NOTION"),
    ("airtable", "Airtable", "https://airtable.com/?ref={code}",        "AFFILIATE_AIRTABLE"),
    ("zapier", "Zapier", "https://zapier.com/?referrer={code}",         "AFFILIATE_ZAPIER"),
    ("make.com", "Make", "https://www.make.com/en/register?pc={code}", "AFFILIATE_MAKE"),
]

# Already injected pattern to avoid double-injection
ALREADY_INJECTED_RE = re.compile(r'\[([^\]]+)\]\(https?://[^\)]+\?(?:ref|r|referrer|pc)=[^\)]+\)')


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [affiliate] {msg}"
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


def load_injections():
    if AFFILIATE_LOG.exists():
        try:
            return json.loads(AFFILIATE_LOG.read_text())
        except Exception:
            pass
    return {}


def save_injections(data):
    tmp = AFFILIATE_LOG.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(AFFILIATE_LOG)


def _devto_get(path: str, api_key: str) -> dict | list:
    req = urllib.request.Request(
        f"{DEVTO_API}{path}",
        headers={"api-key": api_key, "User-Agent": "echo-affiliate/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _devto_put(article_id: int, body_markdown: str, api_key: str) -> bool:
    payload = json.dumps({"article": {"body_markdown": body_markdown}}).encode()
    req = urllib.request.Request(
        f"{DEVTO_API}/articles/{article_id}",
        data=payload,
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "User-Agent": "echo-affiliate/1.0",
        },
        method="PUT"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as e:
        log(f"  PUT failed: {e}")
        return False


def _inject_affiliates(body: str, env: dict) -> tuple[str, int]:
    """
    Add affiliate links the first time a tool is mentioned in the article body.
    Returns (modified_body, injection_count).
    """
    injected = 0

    for keyword, display, url_template, env_key in AFFILIATE_RULES:
        code = env.get(env_key, "")
        if not code:
            continue

        url = url_template.replace("{code}", code)

        # Skip if this tool already has any link in the body
        pattern_linked = re.compile(
            r'\[' + re.escape(display) + r'\]\([^\)]+\)',
            re.IGNORECASE
        )
        if pattern_linked.search(body):
            continue

        # Find first bare mention and linkify it
        bare = re.compile(r'\b' + re.escape(keyword) + r'\b', re.IGNORECASE)
        m = bare.search(body)
        if m:
            original = m.group(0)
            body = body[:m.start()] + f"[{original}]({url})" + body[m.end():]
            injected += 1
            log(f"  injected {keyword} affiliate link")

    return body, injected


def run() -> dict:
    env = load_env()
    api_key = env.get("DEVTO_API_KEY", "")

    if not api_key:
        log("DEVTO_API_KEY not set — skipping")
        return {"status": "no_key"}

    # Check if any affiliate codes are set
    active_codes = [k for _, _, _, k in AFFILIATE_RULES if env.get(k)]
    if not active_codes:
        log("No affiliate codes configured — add AFFILIATE_* keys to golem.env")
        return {"status": "no_affiliate_codes", "hint": "add AFFILIATE_N8N, AFFILIATE_NOTION, etc."}

    injections = load_injections()
    total_injected = 0

    try:
        articles = _devto_get("/articles/me/published?per_page=30", api_key)
    except Exception as e:
        log(f"Failed to fetch articles: {e}")
        return {"status": "error", "error": str(e)}

    for article in articles:
        article_id = article.get("id")
        slug = article.get("slug", "")

        if injections.get(str(article_id), {}).get("done"):
            continue  # already processed

        try:
            full = _devto_get(f"/articles/{article_id}", api_key)
            body = full.get("body_markdown", "")
            if not body:
                continue

            new_body, count = _inject_affiliates(body, env)
            if count == 0:
                injections[str(article_id)] = {"done": True, "injected": 0, "ts": datetime.now().isoformat()}
                continue

            ok = _devto_put(article_id, new_body, api_key)
            if ok:
                log(f"  updated article {slug}: {count} links added")
                injections[str(article_id)] = {
                    "done": True, "injected": count,
                    "ts": datetime.now().isoformat(), "slug": slug
                }
                total_injected += count
            else:
                log(f"  failed to update article {slug}")
        except Exception as e:
            log(f"  error on article {article_id}: {e}")

    save_injections(injections)
    log(f"done — {total_injected} affiliate links injected across {len(articles)} articles")
    return {"total_injected": total_injected, "articles_scanned": len(articles)}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
