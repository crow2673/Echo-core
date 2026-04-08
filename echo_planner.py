#!/usr/bin/env python3
"""
echo_planner.py — Echo's goal planner and task dispatcher
Takes a natural language goal, decomposes into steps via Ollama,
maps steps to existing workers, dispatches in sequence.

Part of the Architecture Leap: Planner → Verify → Reach

Wires into echo_core_daemon.py as a worker.
Does NOT create new loops — Crown the King.
"""
import json
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent

# Decision trace — import safely
try:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("decision_trace", BASE / "core/decision_trace.py")
    _dt = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_dt)
    TRACE_AVAILABLE = True
except Exception:
    _dt = None
    TRACE_AVAILABLE = False
LOG = BASE / "logs/planner.log"
PLAN_HISTORY = BASE / "memory/plan_history.json"

# ── Dispatch table — maps intent to existing workers ──────────────────
DISPATCH_TABLE = {
    "publish":      {"type": "python", "module": "echo_devto_publisher", "args": ["--from-session"]},
    "trade":        {"type": "python", "module": "core.trade_brain",     "args": []},
    "crypto":       {"type": "python", "module": "core.crypto_brain",    "args": []},
    "brief":        {"type": "python", "module": "core.daily_briefing",  "args": []},
    "checkpoint":   {"type": "python", "module": "core.session_checkpoint", "args": []},
    "governor":     {"type": "python", "module": "core.governor_v2",     "args": []},
    "notify":       {"type": "ntfy"},
    "shell":        {"type": "shell"},
    "memory":       {"type": "memory"},
    "file_read":    {"type": "file_read"},
    "file_write":   {"type": "file_write"},
}

INTENT_KEYWORDS = {
    "publish":    ["publish", "write article", "post to dev", "content", "blog"],
    "trade":      ["trade", "buy stock", "sell stock", "portfolio", "stocks"],
    "crypto":     ["crypto", "bitcoin", "ethereum", "btc", "eth", "solana"],
    "brief":      ["briefing", "brief me", "morning report", "status report"],
    "checkpoint": ["checkpoint", "save session", "session summary"],
    "governor":   ["health check", "system state", "update state"],
    "notify":     ["notify", "send message", "alert", "phone", "ntfy"],
    "shell":      ["run", "execute", "command", "bash", "shell"],
    "file_read":  ["read file", "check file", "show file", "cat"],
    "file_write": ["write file", "save to file", "create file"],
}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} — {msg}"
    print(f"[planner] {msg}")
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_plan_history():
    if PLAN_HISTORY.exists():
        return json.loads(PLAN_HISTORY.read_text())
    return []


def save_plan(plan):
    history = load_plan_history()
    history.append(plan)
    history = history[-50:]  # keep last 50 plans
    PLAN_HISTORY.write_text(json.dumps(history, indent=2, default=str))


def classify_intent_local(goal_text):
    """Fast keyword-based intent classification before hitting Ollama."""
    goal_lower = goal_text.lower()
    scores = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in goal_lower)
        if score > 0:
            scores[intent] = score
    if scores:
        return max(scores, key=scores.get)
    return None


def needs_api_reach(goal_text):
    """Determine if this goal needs Claude API vs local model."""
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("echo_reach", BASE / "echo_reach.py")
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        return _mod.should_reach(goal_text)
    except Exception:
        return False

def decompose_goal_ollama(goal_text):
    """Use local Ollama to decompose goal into steps."""
    prompt = f"""You are Echo's planning module. Break this goal into concrete steps.
Each step must map to one of these actions: {list(DISPATCH_TABLE.keys())}.

Goal: {goal_text}

Respond with valid JSON only — no explanation, no markdown:
{{
  "goal": "...",
  "steps": [
    {{"step": 1, "intent": "action_name", "description": "what to do", "params": {{}}}}
  ]
}}"""

    try:
        payload = json.dumps({
            "model": "qwen2.5:32b",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 400}
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
            raw = data.get("response", "").strip()
            # Strip markdown if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
    except Exception as e:
        log(f"Ollama decomposition failed: {e}")
        return None


def execute_step(step):
    """Execute a single plan step using the dispatch table."""
    intent = step.get("intent")
    desc = step.get("description", "")
    params = step.get("params", {})

    if intent not in DISPATCH_TABLE:
        return {"success": False, "error": f"Unknown intent: {intent}"}

    worker = DISPATCH_TABLE[intent]
    worker_type = worker["type"]

    log(f"Executing step: {intent} — {desc}")

    try:
        if worker_type == "python":
            module = worker["module"]
            args = worker.get("args", [])
            result = subprocess.run(
                ["python3", "-m", module] + args,
                capture_output=True, text=True,
                cwd=str(BASE), timeout=300
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[-500:],
                "stderr": result.stderr[-200:] if result.returncode != 0 else ""
            }

        elif worker_type == "ntfy":
            msg = params.get("message", desc)
            req = urllib.request.Request(
                "https://ntfy.sh/echo-alerts",
                data=msg.encode(),
                method="POST"
            )
            urllib.request.urlopen(req, timeout=5)
            return {"success": True, "message": msg}

        elif worker_type == "shell":
            cmd = params.get("command", "")
            if not cmd:
                return {"success": False, "error": "No command provided"}
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=str(BASE), timeout=60
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[-500:],
                "stderr": result.stderr[-200:]
            }

        elif worker_type == "file_read":
            path = params.get("path", "")
            if not path:
                return {"success": False, "error": "No path provided"}
            # Remap common wrong paths to Echo's actual paths
            path_remaps = {
                "/var/log/trading": str(BASE / "logs"),
                "/var/log/echo": str(BASE / "logs"),
                "/tmp/echo": str(BASE / "memory"),
            }
            for wrong, right in path_remaps.items():
                if path.startswith(wrong):
                    path = path.replace(wrong, right)
                    break
            p = Path(path)
            if not p.exists():
                return {"success": False, "error": f"File not found: {path}"}
            content = p.read_text()
            return {"success": True, "content": content[:1000]}

        elif worker_type == "file_write":
            path = params.get("path", "")
            content = params.get("content", "")
            if not path:
                return {"success": False, "error": "No path provided"}
            Path(path).write_text(content)
            return {"success": True}

        elif worker_type == "memory":
            query = params.get("query", "")
            return {"success": True, "note": f"Memory query: {query} (implement later)"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Step timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    return {"success": False, "error": "Unhandled worker type"}


def run_plan(goal_text, use_ollama=True):
    """Main entry — take a goal, decompose, execute, return results."""
    log(f"New goal: {goal_text}")
    plan = {
        "timestamp": datetime.now().isoformat(),
        "goal": goal_text,
        "steps": [],
        "results": [],
        "status": "pending"
    }

    # Try fast local classification first
    quick_intent = classify_intent_local(goal_text)
    if quick_intent and not use_ollama:
        log(f"Quick intent: {quick_intent}")
        plan["steps"] = [{"step": 1, "intent": quick_intent, "description": goal_text, "params": {}}]
    elif use_ollama:
        # Check if this goal needs API reach for better decomposition
        if needs_api_reach(goal_text):
            log("Goal requires deep reasoning — using API reach for decomposition")
            try:
                import importlib.util as _ilu
                _spec = _ilu.spec_from_file_location("echo_reach", BASE / "echo_reach.py")
                _mod = _ilu.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                api_response = _mod.reach(
                    f"Break this goal into steps for an AI agent. Return valid JSON only with keys: goal, steps (list of: step, intent, description, params). Available intents: {list(DISPATCH_TABLE.keys())}. Goal: {goal_text}",
                    force_api=True
                )
                if api_response:
                    import re as _re
                    json_match = _re.search(r'\{.*\}', api_response, _re.DOTALL)
                    if json_match:
                        decomposed = json.loads(json_match.group())
                        if "steps" in decomposed:
                            plan["steps"] = decomposed["steps"]
                            plan["source"] = "claude"
                            log(f"API decomposed into {len(plan['steps'])} steps")
            except Exception as e:
                log(f"API reach for decomposition failed: {e}")

        if not plan.get("steps"):
            decomposed = decompose_goal_ollama(goal_text)
            if decomposed and "steps" in decomposed:
                plan["steps"] = decomposed["steps"]
                plan["source"] = "local"
                log(f"Ollama decomposed into {len(plan['steps'])} steps")
            elif quick_intent:
                log(f"Ollama failed, falling back to quick intent: {quick_intent}")
                plan["steps"] = [{"step": 1, "intent": quick_intent, "description": goal_text, "params": {}}]
                plan["source"] = "fallback"
            else:
                log("Could not classify goal — escalating to Andrew")
                plan["status"] = "escalated"
                save_plan(plan)
                return plan
    else:
        plan["status"] = "escalated"
        save_plan(plan)
        return plan

    # Execute steps
    all_succeeded = True
    for step in plan["steps"]:
        result = execute_step(step)
        plan["results"].append({
            "step": step.get("step"),
            "intent": step.get("intent"),
            "result": result
        })
        if not result.get("success"):
            log(f"Step {step.get('step')} failed: {result.get('error')}")
            all_succeeded = False
            # Continue to next step (validator will handle retries)

    plan["status"] = "complete" if all_succeeded else "partial"
    save_plan(plan)
    log(f"Plan complete — status: {plan['status']}")
    # Record to decision trace
    if TRACE_AVAILABLE and _dt:
        try:
            _dt.trace_plan(plan, source="local")
        except Exception:
            pass
    return plan


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        goal = " ".join(sys.argv[1:])
        result = run_plan(goal, use_ollama=True)
        print(json.dumps(result, indent=2, default=str))
    else:
        # Test with quick classification only
        print("Testing quick intent classification:")
        tests = [
            "publish a new article about the trading brain",
            "run the crypto brain now",
            "send me a phone notification that Echo is healthy",
            "check the system health and update state",
        ]
        for t in tests:
            intent = classify_intent_local(t)
            print(f"  '{t[:50]}' → {intent}")
