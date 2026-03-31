#!/usr/bin/env python3
"""
Echo draft writer — creates a queued dev.to article draft.
Echo calls this when she has a good article idea during reasoning.

Usage:
    python3 -m core.draft_writer --title "My Article Title" --outline "key points"
    python3 -m core.draft_writer --list
"""
import sys, argparse, json
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE / "content"
QUEUE_FILE = BASE / "content/draft_queue.json"

def log_event(summary):
    try:
        from core.event_ledger import log_event as _log
        _log("knowledge", "draft_writer", summary, score=1.0)
    except Exception:
        pass

def list_drafts():
    queue = json.loads(QUEUE_FILE.read_text()) if QUEUE_FILE.exists() else []
    if not queue:
        print("No drafts queued.")
        return
    for i, d in enumerate(queue):
        print(f"  {i+1}. [{d['status']}] {d['title']} — {d['file']}")

def create_draft(title, outline=""):
    CONTENT.mkdir(exist_ok=True)
    slug = title.lower().replace(" ", "_")[:40]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"draft_{ts}_{slug}.md"
    filepath = CONTENT / filename

    # ── Build live context from Echo's actual current state ──
    try:
        from core.event_ledger import query_summary, query_recent
        ledger = query_summary()
        recent = query_recent(limit=5)
        recent_events = "\n".join([
            f"- [{e['event_type']}] {e['source']}: {e['summary'][:80]}"
            for e in recent
        ])
    except Exception:
        ledger = {"total_events": "unknown", "wins": "unknown", "losses": "unknown"}
        recent_events = "no recent events available"

    try:
        import json as _j
        td = _j.loads(Path("/home/andrew/Echo/memory/standing_tasks.json").read_text())
        tasks_str = "\n".join(
            f"- {t['task'][:60]}" for t in td.get("tasks", [])
            if not t.get("disabled") and t.get("weight", 0) > 0
        )
    except Exception:
        tasks_str = "- unknown"

    # Load content strategy — use next queued topic if available
    content_topic = None
    content_angle = None
    try:
        import json as _json
        cs = _json.loads(Path("/home/andrew/Echo/memory/content_strategy.json").read_text())
        next_item = next((q for q in cs.get("queue", []) if q.get("status") in ("next", "queued")), None)
        if next_item:
            content_topic = next_item.get("title")
            content_angle = next_item.get("angle")
            # Mark as in_progress
            for q in cs["queue"]:
                if q.get("id") == next_item["id"]:
                    q["status"] = "in_progress"
            Path("/home/andrew/Echo/memory/content_strategy.json").write_text(_json.dumps(cs, indent=2))
    except Exception:
        pass
    try:
        wc = Path("/home/andrew/Echo/memory/world_context.md").read_text()[:400]
    except Exception:
        wc = "world context unavailable"

    try:
        pub_count = len(list(Path("/home/andrew/Echo/content/published").glob("*.md")))
    except Exception:
        pub_count = 9

    # Override title/outline from content strategy
    if content_topic: title = content_topic
    if content_angle: outline = content_angle
    system_prompt = f"""You are Echo — an autonomous AI agent built by Andrew Elliott, running on a Linux workstation in Mena, Arkansas.

YOUR LIVE STATE RIGHT NOW:
- Events logged: {ledger.get('total_events', 'unknown')}
- Wins: {ledger.get('wins', 'unknown')} | Losses: {ledger.get('losses', 'unknown')}
- Hardware: Ryzen 9 5900X, RTX 3060 12GB, 32GB RAM, Ubuntu
- LLM: qwen2.5:32b via Ollama — fully local, zero cloud
- What you do every 5 minutes:
{tasks_str}
- Recent activity:
{recent_events}
- Articles published: {pub_count}
- Mission: earn passive income so Andrew's wife can come home full time
- Income: Golem Network compute provider (new node penalty phase), dev.to writing, Vast.ai GPU rental

Rules:
- Write in first person as Echo or Andrew
- Use ONLY real numbers from your live state above — never invent statistics
- Be direct and specific — no generic tutorials, no fluff
- Only reference code that actually exists
- If something failed or is broken, say so honestly — that's more interesting than success"""

    prompt = f"""Write a technical dev.to article for developers building autonomous AI systems.

Title: {title}
    {f'Angle and key points: {outline}' if outline else ''}

Current world context (trending now):
{wc[:300]}

    Voice: {content_voice if content_voice else 'Andrew Elliott, Mena Arkansas, no CS degree, honest about failures'}
    Write 800-1200 words in markdown starting with # {title}
Use your actual live numbers. Be honest about what works and what doesn't.
Tags: ai, linux, python, buildinpublic"""

    # ── Generate via 32b model with live context ──
    try:
        from core.providers.router import call_ollama
        import urllib.request, json as _json
        # Warm up the model before generating — prevents cold load timeout
        try:
            warm = _json.dumps({"model":"qwen2.5:32b","prompt":"ready","stream":False}).encode()
            req = urllib.request.Request("http://localhost:11434/api/generate",
                data=warm, headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                _json.loads(r.read())
            print(f"[draft_writer] Model warm, generating draft: {title}")
        except Exception as we:
            print(f"[draft_writer] Warmup note: {we}")
        print(f"[draft_writer] Generating draft: {title}")
        body = call_ollama(prompt, model="qwen2.5:32b", timeout=900.0, system_prompt=system_prompt)
        if not body or len(body) < 100:
            raise ValueError("Model returned empty or too-short response")
    except Exception as e:
        print(f"[draft_writer] Model failed ({e}), writing skeleton instead")
        body = f"""# {title}

{outline if outline else '<!-- Add content here -->'}

## What I Built

## Why It Matters

## The Code

## What's Next
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", type=str)
    parser.add_argument("--outline", type=str, default="")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        list_drafts()
    elif args.title:
        create_draft(args.title, args.outline)
    else:
        parser.print_help()