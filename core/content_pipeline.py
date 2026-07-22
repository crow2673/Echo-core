#!/usr/bin/env python3
"""core/content_pipeline.py — Content generation pipeline.
Generates dev.to articles from content_strategy.json queue.
Invoked by dispatcher as 'content_gen' worker.
"""
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LOG = BASE / "logs/content_pipeline.log"
STRATEGY_FILE = BASE / "memory/content_strategy.json"
AFFILIATE_FILE = BASE / "memory/affiliate_links.json"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def load_strategy():
    if STRATEGY_FILE.exists():
        try:
            return json.loads(STRATEGY_FILE.read_text())
        except Exception:
            pass
    return {"queue": []}


def save_strategy(strategy):
    tmp = STRATEGY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(strategy, indent=2, default=str))
    tmp.rename(STRATEGY_FILE)


def get_next_topic(strategy):
    queue = strategy.get("queue", [])
    pending = [a for a in queue if a.get("status") not in ("published", "generated", "draft")]
    return pending[0] if pending else None


DO_DOC_KEYWORDS = {
    "droplet": "https://docs.digitalocean.com/products/droplets/index.html.md",
    "kubernetes": "https://docs.digitalocean.com/products/kubernetes/index.html.md",
    "app platform": "https://docs.digitalocean.com/products/app-platform/index.html.md",
    "database": "https://docs.digitalocean.com/products/databases/index.html.md",
    "spaces": "https://docs.digitalocean.com/products/spaces/index.html.md",
    "vpc": "https://docs.digitalocean.com/products/networking/vpc/index.html.md",
    "firewall": "https://docs.digitalocean.com/products/networking/firewalls/index.html.md",
}


def fetch_do_doc_context(topic_entry: dict) -> str:
    """Fetch a DigitalOcean docs page as markdown context for article generation.

    Checks topic for explicit 'do_doc_url', then falls back to keyword matching.
    Returns a trimmed markdown snippet (max 2000 chars) or empty string.
    """
    url = topic_entry.get("do_doc_url", "")
    if not url:
        text = (topic_entry.get("title", "") + " " + topic_entry.get("angle", "")).lower()
        for keyword, doc_url in DO_DOC_KEYWORDS.items():
            if keyword in text:
                url = doc_url
                break
    if not url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Echo/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            content = r.read().decode("utf-8", errors="replace")
        # Trim to first 2000 chars to stay within prompt budget
        trimmed = content[:2000].strip()
        log(f"DO doc context fetched: {url} ({len(trimmed)} chars)")
        return f"\n\nREFERENCE (from DigitalOcean docs — use for accuracy, do not copy verbatim):\n{trimmed}\n"
    except Exception as e:
        log(f"DO doc fetch failed ({url}): {e}")
        return ""


def build_affiliate_section() -> str:
    """Load affiliate links and return a markdown Resources section, or empty string."""
    if not AFFILIATE_FILE.exists():
        return ""
    try:
        data = json.loads(AFFILIATE_FILE.read_text())
        links = [l for l in data.get("links", []) if l.get("url") and l.get("text")]
        if not links:
            return ""
        lines = ["\n\n---\n\n## Resources"]
        for l in links:
            lines.append(f"- [{l['text']}]({l['url']})")
        return "\n".join(lines)
    except Exception:
        return ""


def generate_article(topic_entry: dict) -> dict:
    """Use Ollama to generate an article draft."""
    from core.providers.router import call_ollama
    title = topic_entry.get("title", "")
    angle = topic_entry.get("angle", "")
    doc_context = fetch_do_doc_context(topic_entry)
    prompt = (
        f"Write a technical article for dev.to developers.\n\n"
        f"Title: {title}\n"
        f"Core angle: {angle}\n\n"
        + (doc_context if doc_context else "") +
        f"\nSTRICT requirements:\n"
        f"- 600-900 words\n"
        f"- Markdown formatting with ## section headers\n"
        f"- Real, working Python 3 code examples (not pseudocode)\n"
        f"- Must specifically use Ollama (https://ollama.com) for local LLM inference — NOT OpenAI, NOT HuggingFace transformers\n"
        f"- Ollama runs locally via HTTP at http://localhost:11434 — show actual requests.post() calls to it\n"
        f"- The agent should be a Python script that runs as a background process (systemd oneshot or loop), NOT interactive input()\n"
        f"- No 'while True' loops — use systemd timers for scheduling\n"
        f"- No hardcoded API keys\n"
        f"- End with a practical takeaway\n\n"
        f"Output the article body only. Start with the first ## section, no title line."
    )
    body = call_ollama(prompt, model="qwen2.5:32b", timeout=900)
    return {"title": title, "body": body, "angle": angle, "generated_at": datetime.now().isoformat()}


def run(generate=True):
    log("content_pipeline starting")
    strategy = load_strategy()
    topic = get_next_topic(strategy)

    if not topic:
        log("no pending topics in content_strategy.json")
        return

    log(f"next topic: {topic.get('title', '')[:60]}")

    if not generate:
        log("dry run — not generating")
        return

    try:
        article = generate_article(topic)

        if len(article.get("body", "").strip()) < 200:
            log(f"generation produced empty/stub body ({len(article.get('body',''))} chars) — Ollama likely timed out. Aborting.")
            sys.exit(1)

        # Save draft
        drafts_dir = BASE / "content/drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(c for c in topic.get("title", "draft")[:40] if c.isalnum() or c in " -_").strip()
        draft_file = drafts_dir / f"{safe_title}.md"
        affiliate_section = build_affiliate_section()
        draft_file.write_text(f"# {article['title']}\n\n{article['body']}{affiliate_section}")
        if affiliate_section:
            log(f"affiliate links injected ({len(affiliate_section)} chars)")
        log(f"draft saved: {draft_file.name}")

        # Update queue
        for item in strategy["queue"]:
            if item.get("title") == topic.get("title"):
                item["status"] = "draft"
                item["draft_file"] = str(draft_file)
                item["generated_at"] = article["generated_at"]
                break
        save_strategy(strategy)

        # Write pending approval state
        approval_file = BASE / "content/pending_approval.json"
        approval = {
            "draft_file": str(draft_file),
            "title": article["title"],
            "topic_id": topic.get("id", ""),
            "created_at": datetime.now().isoformat(),
            "status": "awaiting_approval",
            "update_offset": 0,
        }
        tmp = approval_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(approval, indent=2))
        tmp.rename(approval_file)

        # Notify Andrew for approval
        preview = article["body"][:300].replace("\n", " ").strip()
        try:
            from core.notifier import notify
            notify(
                "Draft ready for review",
                f'"{article["title"]}"\n\n{preview}...\n\nReply YES to publish or NO to discard.',
            )
            log("approval notification sent")
        except Exception as e:
            log(f"notification failed: {e}")

        try:
            from core.event_ledger import log_event
            log_event("content", "content_pipeline", f"draft: {article['title'][:80]}", score=1.0)
        except Exception:
            pass

    except Exception as e:
        log(f"generation failed: {e}")
        sys.exit(1)

    log("content_pipeline done")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true", default=True)
    args = parser.parse_args()
    run(generate=args.generate)
