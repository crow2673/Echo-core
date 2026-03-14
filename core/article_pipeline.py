#!/usr/bin/env python3
"""
Echo autonomous article pipeline.
Flow:
  1. Pick topic from draft_queue or world_context
  2. Write draft via ollama (echo model)
  3. Self-review via article_reviewer
  4. If fail: rewrite with issues as guidance (max 2 attempts)
  5. If pass: save to content/pending_review/ + notify Andrew via ntfy
  6. Andrew approves via ntfy → publish, or sends feedback → revise

Human is always in the loop before publish.
"""
import json, sys, subprocess, urllib.request
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
DRAFT_QUEUE = BASE / "content/draft_queue.json"
PENDING_DIR = BASE / "content/pending_review"
LOG = BASE / "logs/article_pipeline.log"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default

def is_ollama_idle():
    """Check if Ollama has no active runners — safe to start long inference."""
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/ps",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            result = json.loads(r.read())
            models = result.get("models", [])
            return len(models) == 0
    except Exception:
        return True

def wait_for_ollama_idle(max_wait=300):
    """Wait up to max_wait seconds for Ollama to become idle."""
    import time
    for i in range(max_wait // 10):
        if is_ollama_idle():
            return True
        if i == 0:
            log("  waiting for Ollama to free up...")
        time.sleep(10)
    return False

def call_ollama(prompt, system_prompt, timeout=600):
    """Call echo model via ollama API."""
    try:
        payload = json.dumps({
            "model": "qwen2.5:7b",
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 2048}
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            result = json.loads(r.read())
            return result.get("response", "").strip()
    except Exception as e:
        log(f"ollama error: {e}")
        return None

def write_draft(topic, prompt, issues=None):
    """Write article draft, optionally with revision guidance."""
    system = """You are a developer writing a technical article for dev.to.
Your setup: Ryzen 9 5900X, RTX 3060 12GB, 32GB RAM, Ubuntu Linux, Mena Arkansas.
You run qwen2.5:32b via Ollama locally — no Docker, no cloud, no API costs.
Write in first person ('I', 'my'). Never refer to yourself as 'Andrew'.
Be specific and honest — mention your actual hardware and real experiences.
Never recommend Docker for Ollama — just use: curl -fsSL https://ollama.com/install.sh | sh
Include practical code examples or step-by-step instructions.
Structure: catchy intro, problem/context, solution with code, conclusion.
Target length: 600-1000 words. No duplicate headings. End with a complete conclusion."""

    if issues:
        issue_list = "\n".join(f"- {i}" for i in issues)
        full_prompt = f"""Rewrite this article draft fixing these specific issues:
{issue_list}

Original draft:
{prompt}

Write the complete improved article now."""
    else:
        full_prompt = f"""Write a complete dev.to article about: {topic}

Additional context: {prompt}

Write the full article now, starting with the # title."""

    return call_ollama(full_prompt, system)

def notify_andrew(title, message, tag="article"):
    """Send ntfy notification to Andrew's phone."""
    try:
        sys.path.insert(0, str(BASE))
        from core.notifier import notify
        notify(title, message)
        return True
    except Exception as e:
        log(f"notify failed: {e}")
        return False

def run_single(draft_item):
    """Run pipeline for a single draft queue item."""
    topic = draft_item.get("topic", "unknown topic")
    prompt = draft_item.get("prompt", topic)
    draft_id = draft_item.get("id", f"draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

    log(f"pipeline started: {draft_id}")
    log(f"  topic: {topic[:80]}")

    # Wait for Ollama to be idle — up to 5 minutes
    if not wait_for_ollama_idle(max_wait=300):
        log(f"  ollama busy after 5min wait — skipping")
        return False
    log(f"  ollama idle — starting draft")

    # Import reviewer
    sys.path.insert(0, str(BASE))
    from core.article_reviewer import review

    best_draft = None
    best_score = 0.0
    current_prompt = prompt
    issues = []

    for attempt in range(1, 3):  # max 2 attempts
        log(f"  attempt {attempt}/2: writing draft...")
        text = write_draft(topic, current_prompt, issues=None if attempt == 1 else issues)

        if not text:
            log(f"  attempt {attempt}: ollama returned nothing — skipping")
            continue

        passed, issues, fixes, score = review(text)
        log(f"  attempt {attempt}: score={score:.0%} passed={passed}")

        if score > best_score:
            best_score = score
            best_draft = text

        if passed:
            log(f"  passed review on attempt {attempt}")
            break
        else:
            log(f"  failed — {len(issues)} issues, rewriting...")
            current_prompt = text  # pass draft as input for revision

    if not best_draft:
        log("  pipeline failed — no usable draft produced")
        return False

    # Save to pending_review
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{draft_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path = PENDING_DIR / fname

    # Add metadata header
    meta = f"---\n# PENDING REVIEW\n# Score: {best_score:.0%}\n# Topic: {topic}\n# Created: {datetime.now().isoformat()}\n# To approve: reply 'approve {draft_id}' via ntfy\n---\n\n"
    out_path.write_text(meta + best_draft)

    log(f"  saved to: content/pending_review/{fname}")

    # Notify Andrew
    status = "READY FOR REVIEW" if best_score >= 0.8 else f"NEEDS REVIEW (score: {best_score:.0%})"
    notify_andrew(
        f"Echo Article: {status}",
        f"Draft ready: {topic[:60]}\nFile: {fname}\nScore: {best_score:.0%}\nReply 'approve {draft_id}' to publish"
    )

    # Log to event ledger
    try:
        from core.event_ledger import log_event
        log_event("knowledge", "article_pipeline",
            f"draft ready for review: '{topic[:60]}' score={best_score:.0%}",
            score=best_score)
    except Exception:
        pass

    return True

def run():
    """Process next item from draft_queue."""
    queue = load_json(DRAFT_QUEUE, [])
    pending = [d for d in queue if d.get("status") == "queued"]

    if not pending:
        log("no queued drafts — nothing to do")
        return

    # Take highest priority item
    item = sorted(pending, key=lambda x: x.get("priority", "normal") == "high", reverse=True)[0]
    log(f"processing: {item.get('id', 'unknown')}")

    success = run_single(item)

    # Update queue status
    for d in queue:
        if d.get("id") == item.get("id"):
            d["status"] = "pending_review" if success else "failed"
            d["updated"] = datetime.now().isoformat()

    DRAFT_QUEUE.write_text(json.dumps(queue, indent=2))
    log(f"pipeline {'succeeded' if success else 'failed'}")

if __name__ == "__main__":
    run()
