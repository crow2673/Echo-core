#!/usr/bin/env python3
"""
core/agent_loop.py
==================
Echo's agentic tool loop.

Instead of one Ollama call → reply, this loop:
1. Sends user message to Echo
2. Echo decides if she needs to run a tool
3. If yes: runs the tool, feeds output back to Echo
4. Loops until Echo says she's done
5. Returns final reply

Tools are defined in ~/Echo/docs/actions.json.
Safe actions run automatically.
Unsafe actions require confirmation (or auto-approve if trust=True).
"""

from __future__ import annotations
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ACTIONS_FILE = BASE / "docs" / "actions.json"

TOOL_SYSTEM_ADDENDUM = """
TOOLS AVAILABLE:
You have access to tools you can run on this machine.
To use a tool, respond with a JSON block like this (and nothing else on that line):

TOOL: {{"action": "action_id"}}

After the tool runs, you will receive its output and can continue reasoning.
When you have enough information to answer, respond normally without a TOOL: line.

Available actions:
{action_list}

Rules:
- Only use tools when they would genuinely help answer the question
- Prefer reading before writing or stopping anything
- You may chain multiple tool calls if needed
- When done, give a clear summary of what you found or did
"""


def load_actions() -> dict:
    if not ACTIONS_FILE.exists():
        return {}
    data = json.loads(ACTIONS_FILE.read_text())
    return {a["id"]: a for a in data.get("actions", [])}


def run_action(action: dict, timeout: int = 30) -> str:
    cmd = action.get("cmd", [])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0:
            return f"(exit {result.returncode})\n{out}\n{err}".strip()
        return out if out else "(no output)"
    except subprocess.TimeoutExpired:
        return f"(timed out after {timeout}s)"
    except Exception as e:
        return f"(error: {e})"


def build_action_list_str(actions: dict) -> str:
    lines = []
    for aid, a in actions.items():
        safe = "safe" if a.get("safe", False) else "requires confirmation"
        lines.append(f"  {aid}: {a['label']} [{safe}]")
    return "\n".join(lines)


def parse_tool_call(line: str) -> str | None:
    line = line.strip()
    if not line.startswith("TOOL:"):
        return None
    try:
        payload = json.loads(line[5:].strip())
        return payload.get("action")
    except Exception:
        return None


def agent_loop(
    prompt: str,
    system_prompt: str,
    call_ollama_fn,
    model: str = "qwen2.5:7b",
    timeout: float = 240.0,
    max_iterations: int = 5,
    auto_approve_safe: bool = True,
) -> str:
    """
    Run the agentic loop.
    Returns the final reply string.
    """
    actions = load_actions()
    action_list_str = build_action_list_str(actions)

    # Inject tool instructions into system prompt
    tool_addendum = TOOL_SYSTEM_ADDENDUM.format(action_list=action_list_str)
    full_system = system_prompt + "\n\n" + tool_addendum

    messages = [prompt]
    tool_results = []

    for i in range(max_iterations):
        # Build context with any tool results so far
        if tool_results:
            context = prompt + "\n\n"
            for tr in tool_results:
                context += f"[Tool: {tr['action']}]\n{tr['output']}\n\n"
            current_prompt = context + "Now answer based on the above."
        else:
            current_prompt = prompt

        response = call_ollama_fn(
            prompt=current_prompt,
            model=model,
            timeout=timeout,
            system_prompt=full_system,
        )

        # Check if Echo wants to use a tool
        tool_action = None
        for line in response.splitlines():
            tool_action = parse_tool_call(line)
            if tool_action:
                break

        if not tool_action:
            # No tool call — Echo is done
            return response

        # Tool requested
        if tool_action not in actions:
            tool_results.append({
                "action": tool_action,
                "output": f"(unknown action: {tool_action})"
            })
            continue

        action = actions[tool_action]
        is_safe = action.get("safe", False)

        if not is_safe and not auto_approve_safe:
            # Return asking for confirmation
            return f"I want to run '{action['label']}' but it requires confirmation. Reply 'yes' to proceed."

        # Run the tool
        print(f"[agent] running tool: {tool_action}")
        output = run_action(action)
        print(f"[agent] tool output ({len(output)} chars)")

        tool_results.append({
            "action": tool_action,
            "output": output,
        })

    # Max iterations reached
    return response
