#!/usr/bin/env python3
"""
echo_reach.py — External API bridge for echo_planner.py
When a task exceeds local model capability, routes to Claude API.
Local models handle routine work. Reach handles hard thinking.
Echo stays offline-first. Bridge is a tool she invokes, not a dependency.
Part of the Architecture Leap: Planner → Verify → Reach
"""
import json
import os
import urllib.request
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent
LOG = BASE / "logs/reach.log"
REACH_LOG = BASE / "memory/reach_history.json"

# Tasks that warrant external API — local model can't handle well
REACH_TRIGGERS = [
    "debug",
    "explain why",
    "review this code",
    "what is wrong",
    "analyze",
    "deep review",
    "novel problem",
    "complex reasoning",
    "strategy",
    "should i",
    "what do you think",
]

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[reach] {msg}")
    try:
        with open(LOG, "a") as f:
            f.write(f"{ts} — {msg}\n")
    except Exception:
        pass

def load_reach_history():
    if REACH_LOG.exists():
        return json.loads(REACH_LOG.read_text())
    return []

def save_reach_entry(entry):
    history = load_reach_history()
    history.append(entry)
    history = history[-100:]
    REACH_LOG.write_text(json.dumps(history, indent=2, default=str))

def should_reach(task_text):
    """Determine if this task needs external API vs local model."""
    task_lower = task_text.lower()
    return any(trigger in task_lower for trigger in REACH_TRIGGERS)

def reach_claude(prompt, context="", max_tokens=1000):
    """
    Call Claude API for hard reasoning tasks.
    Returns response text or None on failure.
    Requires ANTHROPIC_API_KEY in environment or golem.env.
    """
    # Load API key from env
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # Try loading from golem.env
        env_file = Path.home() / ".config/echo/golem.env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        log("No ANTHROPIC_API_KEY found — reach unavailable")
        return None

    entry = {
        "timestamp": datetime.now().isoformat(),
        "prompt_preview": prompt[:100],
        "status": "pending"
    }

    try:
        messages = [{"role": "user", "content": prompt}]
        if context:
            messages = [
                {"role": "user", "content": f"Context:\n{context}\n\nTask:\n{prompt}"}
            ]

        payload = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "messages": messages
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            text = data["content"][0]["text"]
            entry["status"] = "success"
            entry["response_preview"] = text[:200]
            save_reach_entry(entry)
            log(f"Claude responded: {text[:80]}...")
            return text

    except Exception as e:
        entry["status"] = "failed"
        entry["error"] = str(e)
        save_reach_entry(entry)
        log(f"Reach failed: {e}")
        return None

def reach_local(prompt, model="qwen2.5:32b"):
    """Fallback to local Ollama when API unavailable."""
    try:
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 600}
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip()
    except Exception as e:
        log(f"Local model failed: {e}")
        return None

def reach(task_text, context="", force_api=False, force_local=False):
    """
    Main entry — intelligently routes to API or local model.
    Returns response text or None.
    """
    log(f"Reach request: {task_text[:60]}")

    if force_local:
        log("Forced local model")
        return reach_local(task_text)

    needs_api = force_api or should_reach(task_text)

    if needs_api:
        log("Routing to Claude API (hard reasoning task)")
        response = reach_claude(task_text, context)
        if response:
            return response
        log("API failed — falling back to local model")

    log("Using local model")
    return reach_local(task_text)

def reach_for_plan_step(step, result, context=""):
    """
    Called by verifier when a step fails and needs AI help to recover.
    Asks the AI what went wrong and what to do next.
    """
    prompt = f"""Echo's planner executed a step and it failed. Help diagnose.

Step intent: {step.get('intent')}
Step description: {step.get('description')}
Result: {json.dumps(result, indent=2)}
Context: {context}

What went wrong? What should Echo do next?
Be concise — 3 sentences max. Focus on actionable next step."""

    return reach(prompt, force_api=False)

if __name__ == "__main__":
    import sys

    print("Testing reach routing:\n")
    tests = [
        ("publish a new article", False),
        ("debug why the trading brain is not entering positions", True),
        ("run the crypto brain", False),
        ("analyze the regret index patterns and explain what they mean", True),
        ("check system health", False),
    ]

    for task, expected_api in tests:
        result = should_reach(task)
        status = "✅" if result == expected_api else "❌"
        route = "API" if result else "local"
        print(f"  {status} '{task[:50]}' → {route}")

    print("\nReach module ready. Add ANTHROPIC_API_KEY to golem.env to enable API bridge.")
