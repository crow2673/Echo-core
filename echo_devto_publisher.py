#!/usr/bin/env python3
"""
echo_devto_publisher.py
=======================
Echo writes and publishes articles to dev.to automatically.

Two modes:
  1. Generate article from recent build session and publish
  2. Generate article on a specific topic and publish

Usage:
    python3 echo_devto_publisher.py --from-session    # article from recent Echo build work
    python3 echo_devto_publisher.py --topic "how to wire an agent loop in Python"
    python3 echo_devto_publisher.py --draft           # write but don't publish yet
    python3 echo_devto_publisher.py --list            # list published articles
"""

import os
import sys
import json
import argparse
import subprocess
import requests
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

# Load API key
def get_api_key() -> str:
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DEV_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("DEV_API_KEY", "")

API_KEY = get_api_key()
API_BASE = "https://dev.to/api"


# ── OLLAMA WRITER ─────────────────────────────────────────────────────────────

def write_article_with_echo(topic: str, context: str = "") -> dict:
    """Ask Echo to write a dev.to article."""

    system = """You are Echo, an AI assistant built by Andrew (crow on dev.to).
You write authentic, technical articles for developers.

Your writing style:
- First person, honest, from real experience
- Specific and technical — real commands, real output, real problems
- No fluff, no filler, no fake enthusiasm
- You share what actually happened, including what broke
- You write for builders like yourself

The author is crow on dev.to. He builds local AI systems on Linux.
His machine: Ryzen 9 5900X, RTX 3060, Ubuntu. He builds Echo — a local AI companion.
He has no coding background — he learned by doing. That's part of the story.

Return ONLY a JSON object with these exact keys:
{
  "title": "article title here",
  "body_markdown": "full article in markdown here",
  "tags": ["tag1", "tag2", "tag3", "tag4"],
  "description": "one sentence description"
}

No preamble. No explanation. JSON only."""

    user = f"""Write a dev.to article about: {topic}

{"Additional context from recent build session:" if context else ""}
{context[:2000] if context else ""}

Write a complete, publishable article. Be specific. Use real technical details.
The article should be 400-800 words. Include code blocks where relevant.
Return only the JSON object."""

    try:
        import requests as _req
        r = _req.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen2.5:7b",
                "stream": False,
                "keep_alive": "30m",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=120,
        )
        r.raise_for_status()
        raw = (r.json().get("message", {}) or {}).get("content", "").strip()
    except Exception as e:
        print(f"[publisher] Ollama error: {e}")
        return {}

    # Try to extract JSON
    import re
    raw = re.sub(r'^```(json)?\s*', '', raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r'\s*```$', '', raw).strip()

    # Find JSON object
    m = re.search(r'\{.*\}', raw, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            try:
                import ast
                # Fix common control character issues
                cleaned = m.group(0).replace("\r", "\\r").replace("\t", "\\t")
                return json.loads(cleaned)
            except Exception as e:
                print(f"[publisher] JSON parse error: {e}")
                print(f"[publisher] Raw output: {raw[:500]}")
                # Extract fields manually
                title = re.search(r'"title"\s*:\s*"([^"]+)"', raw)
                body = re.search(r'"body_markdown"\s*:\s*"(.*?)(?<!\\)"', raw, re.DOTALL)
                tags = re.findall(r'"([a-z]+)"', raw[raw.find('tags'):raw.find('tags')+200]) if 'tags' in raw else ['linux', 'ai']
                desc = re.search(r'"description"\s*:\s*"([^"]+)"', raw)
                if title and body:
                    return {
                        "title": title.group(1),
                        "body_markdown": body.group(1).replace("\\n", "\n"),
                        "tags": tags[:4] or ['linux', 'ai', 'python'],
                        "description": desc.group(1) if desc else ""
                    }
                return {}

    return {}


# ── SESSION CONTEXT ───────────────────────────────────────────────────────────

def get_recent_session_context() -> str:
    """Pull build context from CHANGELOG and architecture memories."""
    parts = []

    # Primary: CHANGELOG - most accurate record of what was built
    changelog = BASE / "CHANGELOG.md"
    if changelog.exists():
        parts.append("=== RECENT BUILD LOG ===")
        parts.append(changelog.read_text()[-4000:])

    # Secondary: architecture memories
    try:
        import sqlite3
        conn = sqlite3.connect(str(BASE / "echo_semantic_memory.sqlite"))
        rows = conn.execute(
            """SELECT text FROM memories
               WHERE (text LIKE '%architecture%' OR text LIKE '%agent%' 
               OR text LIKE '%daemon%' OR text LIKE '%memory%'
               OR text LIKE '%voice%' OR text LIKE '%Golem%')
               AND text NOT LIKE '%screen content unclear%'
               ORDER BY created_at DESC LIMIT 15"""
        ).fetchall()
        conn.close()
        if rows:
            parts.append("=== ECHO ARCHITECTURE CONTEXT ===")
            parts.append("\n".join(r[0] for r in rows[:10]))
    except Exception as e:
        print(f"[publisher] Memory read error: {e}")

    return "\n\n".join(parts)


# ── DEV.TO API ────────────────────────────────────────────────────────────────

def publish_article(title: str, body: str, tags: list,
                    description: str = "", published: bool = True) -> dict:
    """Publish article to dev.to."""
    if not API_KEY:
        print("[publisher] ERROR: DEV_API_KEY not found")
        return {}

    payload = {
        "article": {
            "title": title,
            "body_markdown": body,
            "published": published,
            "tags": [t.replace("-","").replace(" ","")[:20] for t in tags[:4]],  # dev.to: no hyphens
            "description": description,
        }
    }

    r = requests.post(
        f"{API_BASE}/articles",
        json=payload,
        headers={"api-key": API_KEY, "Content-Type": "application/json"},
        timeout=30,
    )

    if r.status_code in (200, 201):
        data = r.json()
        return {
            "id": data.get("id"),
            "title": data.get("title"),
            "url": data.get("url"),
            "published": data.get("published"),
        }
    else:
        print(f"[publisher] API error {r.status_code}: {r.text[:200]}")
        return {}


def list_articles() -> list:
    """List published articles."""
    r = requests.get(
        f"{API_BASE}/articles/me",
        headers={"api-key": API_KEY},
        timeout=10,
    )
    if r.status_code == 200:
        return r.json()
    return []


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Echo dev.to Publisher")
    parser.add_argument("--from-session", action="store_true",
                        help="Write article from recent build session")
    parser.add_argument("--topic", type=str,
                        help="Write article on specific topic")
    parser.add_argument("--draft", action="store_true",
                        help="Save as draft, don't publish")
    parser.add_argument("--file", type=str, help="Publish a specific markdown file")
    parser.add_argument("--list", action="store_true",
                        help="List published articles")
    args = parser.parse_args()

    if args.list:
        articles = list_articles()
        print(f"\n{'='*50}")
        print(f"  Articles for crow ({len(articles)} total)")
        print(f"{'='*50}")
        for a in articles:
            status = "✅ published" if a.get("published") else "📝 draft"
            views = a.get("page_views_count", 0)
            print(f"  {status} | {views:>5} views | {a['title']}")
        return

    # Determine topic
    if args.file:
        import os
        fpath = Path(args.file)
        if not fpath.exists():
            print(f"File not found: {args.file}")
            sys.exit(1)
        content_md = fpath.read_text()
        # Extract title from first # heading
        lines = content_md.splitlines()
        title = next((l.lstrip("# ") for l in lines if l.startswith("# ")), fpath.stem)
        article = {
            "title": title,
            "body_markdown": content_md,
            "tags": ["ai", "linux", "devjournal", "buildinpublic"],
            "description": title
        }
        print(f"[publisher] Publishing file: {fpath.name}")
        print(f"[publisher] Title: {title}")
        published = not args.draft
        result = publish_article(article["title"], article["body_markdown"], article["tags"], article["description"], published=published)
        if result:
            print(f"[publisher] Published: {result.get('url', 'unknown')}")
        sys.exit(0)
    if args.from_session:
        # Check content_strategy.json for next queued topic first
        import json as _json
        _strategy_file = BASE / "memory/content_strategy.json"
        _strategy_topic = None
        _strategy_angle = None
        if _strategy_file.exists():
            try:
                _cs = _json.loads(_strategy_file.read_text())
                _next = next((q for q in _cs.get("queue", []) if q.get("status") in ("next", "queued")), None)
                if _next:
                    _strategy_topic = _next.get("title")
                    _strategy_angle = _next.get("angle", "")
                    # Mark as in_progress
                    for q in _cs["queue"]:
                        if q.get("id") == _next["id"]:
                            q["status"] = "in_progress"
                    _strategy_file.write_text(_json.dumps(_cs, indent=2))
                    print(f"[publisher] Using content strategy topic: {_strategy_topic}")
            except Exception as _e:
                print(f"[publisher] Content strategy read failed: {_e}")

        print("[publisher] Reading recent build session...")
        context = get_recent_session_context()
        if _strategy_angle:
            context = f"Article angle: {_strategy_angle}\n\n{context}"
        topic = _strategy_topic or "building a local AI assistant on Linux — recent progress on Echo"
        print(f"[publisher] Topic: {topic[:80]}")
        print(f"[publisher] Context: {len(context)} chars from recent memory")
    elif args.topic:
        topic = args.topic
        context = ""
    else:
        parser.print_help()
        return

    print(f"[publisher] Writing article: {topic}")
    print("[publisher] Asking Echo to write... (this takes 2-4 minutes)")

    article = write_article_with_echo(topic, context)

    if not article or "title" not in article:
        print("[publisher] Failed to generate article")
        return

    title = article.get("title", "Untitled")
    body = article.get("body_markdown", "")
    tags = article.get("tags", ["linux", "ai", "python"])
    description = article.get("description", "")

    print(f"\n{'='*50}")
    print(f"  ARTICLE READY")
    print(f"{'='*50}")
    print(f"  Title: {title}")
    print(f"  Tags: {tags}")
    print(f"  Length: {len(body)} chars")
    print(f"  Description: {description}")
    print(f"{'='*50}")
    print(f"\nFirst 300 chars:\n{body[:300]}...")

    # Save locally
    output_dir = BASE / "content"
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    local_file = output_dir / f"article_{ts}.md"
    local_file.write_text(f"# {title}\n\n{body}")
    print(f"\n[publisher] Saved locally: {local_file}")

    if args.draft:
        print("[publisher] Draft mode — not publishing")
        result = publish_article(title, body, tags, description, published=False)
        if result:
            print(f"[publisher] Draft saved: {result.get('url')}")
    else:
        print("[publisher] Publishing...")
        result = publish_article(title, body, tags, description, published=True)
        if result:
            print(f"[publisher] ✅ Published: {result.get('url')}")
            # Seed into Echo's memory
            try:
                from echo_memory_sqlite import get_memory
                get_memory().add(
                    f"Published dev.to article: '{title}' at {result.get('url')}",
                    {"type": "content", "priority": "medium"}
                )
            except Exception:
                pass
        else:
            print("[publisher] ❌ Publish failed")


if __name__ == "__main__":
    main()
