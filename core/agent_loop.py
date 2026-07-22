#!/usr/bin/env python3
"""
core/agent_loop.py — Real tool-calling agent loop for Echo.

Echo thinks → calls a tool → observes result → thinks again → repeats until done.
Tools: web_search, read_file, write_file, notify_andrew, run_script.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from core.providers.router import call_ollama

# ── Tool definitions ───────────────────────────────────────────────────────────

TOOLS_SPEC = """
You have access to the following tools. Call them by outputting exactly:
TOOL: <tool_name>
ARGS: <json args>

Available tools:
- web_search: {"query": "search terms"} — search the web for information
- list_files: {"path": "memory", "pattern": "*audit*"} — discover files inside ~/Echo/ using a bounded glob
- search_files: {"path": "memory", "pattern": "*.json", "query": "prediction_calibration"} — find relevant local evidence by content
- read_file: {"path": "relative/path", "tail_lines": 0} — read a file inside ~/Echo/; set tail_lines for recent content
- read_json: {"path": "memory/report.json", "key_path": "checks.prediction_calibration"} — inspect a specific JSON value without truncating unrelated content
- write_file: {"path": "relative/path", "content": "text"} — write a file inside ~/Echo/memory/ or ~/Echo/logs/
- verify_json_stats: {"path": "memory/result.json", "values_key": "values"} — independently verify count, sum, minimum, and maximum fields against a numeric list
- notify_andrew: {"message": "text"} — send Andrew a Telegram message (use sparingly, only when stuck or done)
- run_script: {"path": "tools/system_health.py"} — run an existing deployed script in ~/Echo/

When you have enough information and are done reasoning, output your final answer without a TOOL: line.
Only call one tool per response. Be specific about what you're looking for.
Never imitate or invent tool transcript markers such as "[You called: ...]" or "[Result: ...]".
To use a tool, emit a real TOOL/ARGS call and wait for its returned result.
Never claim a goal is complete merely because you described a plan or attempted an action.
You may use any available safe method, including methods not anticipated by the task author.
Claim completion only when genuine outcome evidence verifies the success criterion.
Clearly label unverified results as unverified.
An exit code, hash change, deployment, or activity log proves activity, not correctness.
Use independent invariants or external outcomes to verify correctness.
"""

ALLOWED_WRITE_PATHS = ["memory/", "logs/"]
ALLOWED_RUN_PATHS = ["tools/", "builds/deployed/"]


def _resolve_allowed_path(path: str, allowed_prefixes: list[str]) -> Path | None:
    """Resolve a relative path and reject traversal outside allowed directories."""
    try:
        full = (BASE / path).resolve()
        for prefix in allowed_prefixes:
            allowed = (BASE / prefix).resolve()
            if full == allowed or full.is_relative_to(allowed):
                return full
    except (OSError, ValueError):
        pass
    return None


def _tool_web_search(args: dict) -> str:
    try:
        from core.web_search import search
        query = args.get("query", "")
        results = search(query, max_results=5)
        if not results:
            return "No results found."
        lines = []
        for r in results[:5]:
            lines.append(f"- {r.get('title','')}: {r.get('url','')}\n  {r.get('body','')[:200]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"


def _tool_read_file(args: dict) -> str:
    try:
        path = args.get("path", "")
        full = (BASE / path).resolve()
        if not full.is_relative_to(BASE):
            return "Read denied: path must be inside ~/Echo/"
        if not full.exists():
            return f"File not found: {path}"
        content = full.read_text()
        tail_lines = int(args.get("tail_lines", 0) or 0)
        if tail_lines > 0:
            content = "\n".join(content.splitlines()[-min(tail_lines, 200):])
        if len(content) > 1400:
            content = (
                content[:1250]
                + "\n...[truncated: use read_json with key_path, search_files by content, "
                "or read_file with tail_lines instead of rereading the same file]"
            )
        return content
    except Exception as e:
        return f"Read error: {e}"


def _tool_read_json(args: dict) -> str:
    try:
        path = args.get("path", "")
        full = (BASE / path).resolve()
        if not full.is_relative_to(BASE):
            return "JSON read denied: path must be inside ~/Echo/"
        value = json.loads(full.read_text())
        key_path = args.get("key_path", "")
        for key in [part for part in key_path.split(".") if part]:
            value = value[int(key)] if isinstance(value, list) else value[key]
        return json.dumps(value, indent=2)[:6000]
    except Exception as e:
        return f"JSON read error: {e}"


def _tool_list_files(args: dict) -> str:
    try:
        path = args.get("path", ".")
        pattern = args.get("pattern", "*")
        full = (BASE / path).resolve()
        if not full.is_relative_to(BASE):
            return "List denied: path must be inside ~/Echo/"
        if not full.is_dir():
            return f"Directory not found: {path}"
        matches = sorted(item for item in full.glob(pattern) if item.is_file())[:100]
        return "\n".join(str(item.relative_to(BASE)) for item in matches) or "No matching files."
    except Exception as e:
        return f"List error: {e}"


def _tool_search_files(args: dict) -> str:
    try:
        path = args.get("path", ".")
        pattern = args.get("pattern", "*")
        query = str(args.get("query", "")).lower()
        full = (BASE / path).resolve()
        if not full.is_relative_to(BASE):
            return "Search denied: path must be inside ~/Echo/"
        if not query:
            return "Search error: query is required"
        matches = []
        for item in sorted(full.glob(pattern))[:500]:
            if not item.is_file() or item.stat().st_size > 2_000_000:
                continue
            try:
                for line_number, line in enumerate(item.read_text(errors="replace").splitlines(), 1):
                    if query in line.lower():
                        matches.append(f"{item.relative_to(BASE)}:{line_number}: {line.strip()[:240]}")
                        if len(matches) >= 50:
                            return "\n".join(matches)
            except OSError:
                continue
        return "\n".join(matches) or "No matching content."
    except Exception as e:
        return f"Search error: {e}"


def _tool_write_file(args: dict) -> str:
    try:
        path = args.get("path", "")
        content = args.get("content", "")
        full = _resolve_allowed_path(path, ALLOWED_WRITE_PATHS)
        if full is None:
            return f"Write denied: path must be under {ALLOWED_WRITE_PATHS}"
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        return f"Written: {path} ({len(content)} chars)"
    except Exception as e:
        return f"Write error: {e}"


def _tool_verify_json_stats(args: dict) -> str:
    """Independently validate derived statistics in a JSON artifact."""
    try:
        path = args.get("path", "")
        values_key = args.get("values_key", "values")
        full = (BASE / path).resolve()
        if not full.is_relative_to(BASE):
            return "Verification denied: path must be inside ~/Echo/"
        data = json.loads(full.read_text())
        values = data[values_key]
        if not isinstance(values, list) or not values or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) for value in values
        ):
            return "Verification failed: values must be a non-empty numeric list."
        expected = {
            "count": len(values),
            "sum": sum(values),
            "minimum": min(values),
            "maximum": max(values),
        }
        actual = {key: data.get(key) for key in expected}
        return json.dumps({
            "verified": actual == expected,
            "expected": expected,
            "actual": actual,
        })
    except Exception as e:
        return f"Verification error: {e}"


def _tool_notify_andrew(args: dict) -> str:
    try:
        from core.notifier import notify
        msg = args.get("message", "")[:500]
        notify("Echo", msg)
        return "Andrew notified."
    except Exception as e:
        return f"Notify error: {e}"


def _tool_run_script(args: dict) -> str:
    import subprocess
    try:
        path = args.get("path", "")
        full = _resolve_allowed_path(path, ALLOWED_RUN_PATHS)
        if full is None:
            return f"Run denied: path must be under {ALLOWED_RUN_PATHS}"
        if not full.exists():
            return f"Script not found: {path}"
        result = subprocess.run(
            [sys.executable, str(full)],
            cwd=str(BASE),
            capture_output=True, text=True, timeout=60
        )
        out = (result.stdout + result.stderr)[:1000]
        return out if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Script timed out (60s)"
    except Exception as e:
        return f"Run error: {e}"


TOOLS = {
    "web_search": _tool_web_search,
    "list_files": _tool_list_files,
    "search_files": _tool_search_files,
    "read_file": _tool_read_file,
    "read_json": _tool_read_json,
    "write_file": _tool_write_file,
    "verify_json_stats": _tool_verify_json_stats,
    "notify_andrew": _tool_notify_andrew,
    "run_script": _tool_run_script,
}

MUTATING_TOOLS = {"write_file"}
VERIFICATION_TOOLS = {"verify_json_stats"}


def _verification_passed(tool_name: str, result: str) -> bool:
    if tool_name == "verify_json_stats":
        try:
            return json.loads(result).get("verified") is True
        except (json.JSONDecodeError, AttributeError):
            return False
    return False


def _parse_tool_call(response: str):
    """Extract TOOL: and ARGS: from response. Returns (tool_name, args_dict) or (None, None)."""
    tool_match = re.search(r"TOOL:\s*(\w+)", response)
    if not tool_match:
        return None, None
    tool_name = tool_match.group(1).strip()
    args = {}
    args_marker = re.search(r"ARGS:\s*", response)
    if args_marker:
        try:
            args, _ = json.JSONDecoder().raw_decode(response[args_marker.end():].lstrip())
        except (json.JSONDecodeError, TypeError):
            args = {}
    return tool_name, args


# ── Main agent loop ────────────────────────────────────────────────────────────

def agent_loop(
    prompt: str,
    system_prompt: str = "",
    call_ollama_fn=None,
    model: str = "qwen2.5:32b",
    timeout: float = 180.0,
    max_iterations: int = 5,
    auto_approve_safe: bool = True,
    return_report: bool = False,
    outcome_verifier=None,
    success_criteria: str = "",
) -> str:
    fn = call_ollama_fn or call_ollama

    full_system = (system_prompt + "\n\n" + TOOLS_SPEC).strip()

    base_prompt = prompt
    conversation = prompt
    trace = []
    notes = []
    final_answer = ""
    status = "incomplete"
    mutation_index = -1
    verification_index = -1
    latest_outcome_verified = False
    evidence = []
    empty_retries = 0
    seen_tool_calls = set()

    def task_state_block() -> str:
        inspected = []
        changed = []
        for item in trace:
            path = item.get("args", {}).get("path")
            if not path:
                continue
            if item["tool"] in {"read_file", "read_json", "list_files", "search_files"}:
                inspected.append(path)
            if item["tool"] in MUTATING_TOOLS:
                changed.append(path)
        latest = evidence[-1] if evidence else None
        unresolved = {}
        if latest and latest.get("passed") is not True:
            unresolved = {
                key: value for key, value in latest.items()
                if key not in {"after_tool_index", "criteria", "passed"}
                and (value is False or value is None or key in {"error", "reason"})
            }
        return (
            "\n\n[TASK STATE - CURRENT SOURCE OF TRUTH]\n"
            f"Success criteria: {success_criteria or 'not explicitly supplied'}\n"
            f"Inspected paths: {json.dumps(list(dict.fromkeys(inspected))[-12:])}\n"
            f"Changed paths: {json.dumps(list(dict.fromkeys(changed))[-8:])}\n"
            f"Latest outcome evaluation: {json.dumps(latest, default=str)[:1800] if latest else 'not run'}\n"
            f"Unresolved requirements: {json.dumps(unresolved, default=str)[:1000]}\n"
            "Choose any safe method, but prioritize satisfying unresolved requirements. "
            "Do not substitute a plausible secondary issue for an explicitly failed criterion.\n"
        )

    def rebuild_conversation() -> str:
        recent = "\n\n".join(notes[-6:])
        return base_prompt + task_state_block() + (f"\n\n[RECENT ACTIONS]\n{recent}" if recent else "")

    def evaluate_outcome(after_index: int) -> bool:
        nonlocal latest_outcome_verified, verification_index
        if outcome_verifier is None:
            return False
        try:
            result = outcome_verifier()
            if not isinstance(result, dict):
                result = {"passed": bool(result), "detail": str(result)}
        except Exception as exc:
            result = {"passed": False, "error": str(exc)}
        result = {
            "after_tool_index": after_index,
            "criteria": success_criteria,
            **result,
        }
        evidence.append(result)
        if result.get("passed") is True:
            verification_index = after_index
            latest_outcome_verified = True
            return True
        return False

    for iteration in range(max_iterations):
        conversation = rebuild_conversation()
        response = fn(
            prompt=conversation,
            model=model,
            timeout=timeout,
            system_prompt=full_system,
        )

        if not response:
            if empty_retries < 1:
                empty_retries += 1
                notes.append(
                    "[Transient model failure: no response returned. Resume from current task state; "
                    "do not restart or claim completion.]"
                )
                continue
            status = "model_returned_empty"
            break
        empty_retries = 0

        tool_name, args = _parse_tool_call(response)

        if not tool_name or tool_name not in TOOLS:
            if outcome_verifier is not None and not latest_outcome_verified:
                evaluate_outcome(mutation_index)
            if (mutation_index >= 0 or outcome_verifier is not None) and not latest_outcome_verified:
                notes.append(
                    f"[Unsupported completion claim: {response[:1000]}]\n"
                    + "Completion rejected because no passing independent verification occurred "
                    + "after the latest mutation. Address the unresolved task-state requirements."
                )
                status = "unverified"
                continue
            final_answer = response
            status = "completed"
            break

        tool_fn = TOOLS[tool_name]
        call_key = (tool_name, json.dumps(args, sort_keys=True, default=str))
        if call_key in seen_tool_calls:
            tool_result = (
                "Repeated identical tool call blocked. Use a different safe method or narrower "
                "query; repeating the same observation cannot create new evidence."
            )
        else:
            seen_tool_calls.add(call_key)
            try:
                tool_result = tool_fn(args)
            except Exception as e:
                tool_result = f"Tool execution error: {e}"
        trace.append({
            "iteration": iteration + 1,
            "tool": tool_name,
            "args": args,
            "result": tool_result[:1500],
        })
        if tool_name in MUTATING_TOOLS:
            mutation_index = len(trace) - 1
            latest_outcome_verified = False
            if outcome_verifier is not None:
                passed = evaluate_outcome(mutation_index)
                notes.append(
                    "[Automatic outcome evaluation: "
                    + json.dumps(evidence[-1])[:1500]
                    + "]\n"
                    + (
                        "The success criteria are satisfied. You may finish honestly."
                        if passed else
                        "The success criteria are not yet satisfied. Continue using any safe method."
                    )
                )
        if tool_name in VERIFICATION_TOOLS and _verification_passed(tool_name, tool_result):
            verification_index = len(trace) - 1
            latest_outcome_verified = True
            evidence.append({
                "after_tool_index": len(trace) - 1,
                "criteria": success_criteria,
                "passed": True,
                "source": tool_name,
                "result": tool_result[:1500],
            })

        notes.append(
            f"[You called: {tool_name}({json.dumps(args)})]\n"
            + f"[Result: {tool_result[:1500]}]\n\n"
            + "Continue reasoning based on the tool result above."
        )
    else:
        status = "iteration_limit"

    report = {
        "generated_at": datetime.now().isoformat(),
        "status": status,
        "verified": status == "completed" and (
            (mutation_index == -1 and outcome_verifier is None) or latest_outcome_verified
        ),
        "final_answer": final_answer,
        "tool_calls": trace,
        "mutation_performed": mutation_index >= 0,
        "verification_after_mutation": mutation_index >= 0 and latest_outcome_verified,
        "success_criteria": success_criteria,
        "outcome_evidence": evidence,
    }
    # Persist only genuinely independent-verification traces. Read-only tasks with
    # no verifier may be report-level "verified", but are not training evidence.
    trace_status = (
        "completed_verified"
        if status == "completed" and latest_outcome_verified
        else status
    )
    try:
        from core.reasoning_trace_collector import save_verified_trace
        save_verified_trace(base_prompt, trace, trace_status, evidence, final_answer)
    except Exception:
        pass
    return report if return_report else (
        final_answer if final_answer else f"[agent_loop {status}: no verified final answer]"
    )
