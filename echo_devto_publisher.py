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
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

DEVTO_API = "https://dev.to/api"


def get_api_key():
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DEV_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def write_article_with_echo(topic: str, context: str = "") -> dict:
    """Use Ollama to write an article. Returns {title, body, tags}."""
    from core.providers.router import call_ollama

    prompt = (
        f"You are Echo, an AI engineer writing for dev.to.\n\n"
        f"Write a complete, well-structured technical article about: {topic}\n\n"
        f"Requirements:\n"
        f"- Title: compelling, SEO-friendly\n"
        f"- Body: 600-1000 words, markdown format, code examples where relevant\n"
        f"- Tags: 4 relevant dev.to tags (comma-separated)\n"
        f"- Audience: developers and AI tinkerers\n\n"
        f"Context from recent work:\n{context[:500]}\n\n"
        f"Output format (strict):\n"
        f"TITLE: ...\n"
        f"TAGS: ...\n"
        f"---\n"
        f"(article body here)"
    )

    response = call_ollama(prompt, model="qwen2.5:32b", timeout=180)
    if not response:
        raise RuntimeError("Ollama returned empty response")

    lines = response.splitlines()
    title = ""
    tags = []
    body_lines = []
    in_body = False

    for line in lines:
        if line.startswith("TITLE:"):
            title = line.split(":", 1)[1].strip()
        elif line.startswith("TAGS:"):
            tags = [t.strip() for t in line.split(":", 1)[1].split(",")][:4]
        elif line.strip() == "---":
            in_body = True
        elif in_body:
            body_lines.append(line)

    if not title:
        title = f"Echo: {topic[:60]}"
    body = "\n".join(body_lines).strip()
    if not body:
        body = response

    return {"title": title, "body": body, "tags": tags}


def get_recent_session_context() -> str:
    """Pull context from recent Echo build work."""
    parts = []
    try:
        changelog = BASE / "CHANGELOG.md"
        if changelog.exists():
            lines = changelog.read_text().splitlines()[:20]
            parts.append("Recent changes:\n" + "\n".join(lines))
    except Exception:
        pass
    try:
        summary_file = BASE / "memory/session_summary.json"
        if summary_file.exists():
            s = json.loads(summary_file.read_text())
            focus = s.get("focus", "")
            if focus:
                parts.append(f"Session focus: {focus}")
    except Exception:
        pass
    return "\n".join(parts)


def publish_article(title: str, body: str, tags: list, draft: bool = False) -> dict:
    """Publish or save as draft to dev.to. Returns API response."""
    import urllib.request
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("DEV_API_KEY not set in golem.env")

    payload = json.dumps({
        "article": {
            "title": title,
            "body_markdown": body,
            "published": not draft,
            "tags": tags[:4],
        }
    }).encode()

    req = urllib.request.Request(
        f"{DEVTO_API}/articles",
        data=payload,
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def list_articles():
    """List published articles."""
    import urllib.request
    api_key = get_api_key()
    if not api_key:
        print("DEV_API_KEY not set")
        return

    req = urllib.request.Request(
        f"{DEVTO_API}/articles/me",
        headers={"api-key": api_key, "User-Agent": "Echo/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        articles = json.loads(r.read())

    print(f"\n{len(articles)} articles on dev.to:")
    for a in articles:
        views = a.get("page_views_count", 0)
        reactions = a.get("positive_reactions_count", 0)
        print(f"  [{views}v {reactions}r] {a.get('title', 'untitled')[:60]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-session", action="store_true", help="Article from recent build session")
    parser.add_argument("--topic", default="", help="Article topic")
    parser.add_argument("--draft", action="store_true", help="Save as draft, don't publish")
    parser.add_argument("--list", action="store_true", help="List published articles")
    args = parser.parse_args()

    if args.list:
        list_articles()
        return

    if not args.from_session and not args.topic:
        parser.print_help()
        sys.exit(1)

    topic = args.topic
    context = ""
    if args.from_session:
        context = get_recent_session_context()
        if not topic:
            topic = "Building an autonomous AI agent on Linux with local LLMs"

    print(f"Writing article: {topic[:60]}...")
    article = write_article_with_echo(topic, context)
    print(f"Title: {article['title']}")
    print(f"Tags: {article['tags']}")
    print(f"Body: {len(article['body'])} chars")

    mode = "draft" if args.draft else "published"
    print(f"\nPublishing as {mode}...")
    try:
        result = publish_article(article["title"], article["body"], article["tags"], draft=args.draft)
        url = result.get("url", "")
        print(f"Success! {url}")
        try:
            from core.event_ledger import log_event
            log_event("content", "devto_publisher", f"{mode}: {article['title'][:80]}", score=1.0)
        except Exception:
            pass
    except Exception as e:
        print(f"Publish failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
