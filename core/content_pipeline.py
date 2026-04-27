#!/usr/bin/env python3
"""core/content_pipeline.py — Content generation pipeline.
Generates dev.to articles from content_strategy.json queue.
Invoked by dispatcher as 'content_gen' worker.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LOG = BASE / "logs/content_pipeline.log"
STRATEGY_FILE = BASE / "memory/content_strategy.json"


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


def generate_article(topic_entry: dict) -> dict:
    """Use Ollama to generate an article draft."""
    from core.providers.router import call_ollama
    title = topic_entry.get("title", "")
    angle = topic_entry.get("angle", "")
    prompt = (
        f"Write a technical dev.to article.\n"
        f"Title: {title}\n"
        f"Angle: {angle}\n\n"
        f"Requirements: 600-900 words, markdown, code examples, dev.to audience.\n"
        f"Output the article body only (no title line)."
    )
    body = call_ollama(prompt, model="qwen2.5:32b", timeout=300)
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
        # Save draft
        drafts_dir = BASE / "content/drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(c for c in topic.get("title", "draft")[:40] if c.isalnum() or c in " -_").strip()
        draft_file = drafts_dir / f"{safe_title}.md"
        draft_file.write_text(f"# {article['title']}\n\n{article['body']}")
        log(f"draft saved: {draft_file.name}")

        # Update queue
        for item in strategy["queue"]:
            if item.get("title") == topic.get("title"):
                item["status"] = "draft"
                item["draft_file"] = str(draft_file)
                item["generated_at"] = article["generated_at"]
                break
        save_strategy(strategy)

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
