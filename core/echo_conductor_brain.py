#!/usr/bin/env python3
"""core/echo_conductor_brain.py — Echo decides who handles Andrew's message.

This is the orchestration layer on top of core/conductor.py (the tmux relay).
Andrew sends ONE message to Echo (via Telegram). Echo's brain:
  1. routes it — answer herself, or wake Claude, or wake Codex, or both
  2. if relaying: types it into that agent's tmux pane (conductor.relay) and
     watches the shared bus for their reply
  3. returns a single answer for Andrew — so he talks to one place (Echo) and
     the right AI handles it under the hood.

Public:
  route(text) -> {"target": ..., "relay_text": ..., "reason": ...}
  conduct(text, timeout=150) -> str        # full handle: route -> relay -> reply

Loop guard: only Andrew-originated messages are conducted; agent bus replies
never re-enter here.
"""
import sys, json, time, re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
CHANNEL = BASE / "collab/channel.jsonl"

VALID = ("self", "claude", "codex", "both", "broadcast")

# ADDRESSING (not mere mention): @name, name at the start, or "ask/tell/have name".
# A bare "claude" in the middle of a sentence is a mention, not an address.
# Imperatives only ("ask/tell/route to claude ..."). NOT "have/get" — those fire on
# possessive mentions like "i have claude in the background", which is a mention, not an address.
_ADDR_CLAUDE = re.compile(r"(?:@claude\b|^\s*claude\b|\b(?:ask|tell|route\s+to)\s+claude\b)", re.I)
_ADDR_CODEX = re.compile(r"(?:@codex\b|^\s*codex\b|\b(?:ask|tell|route\s+to)\s+codex\b)", re.I)
# BROADCAST intent: "let the other two know", "tell them", "let everyone know"...
_BROADCAST = re.compile(
    r"\b(?:let\s+(?:the\s+)?(?:other|others|other\s+two|everyone|both|guys)[^.]*\bknow"
    r"|tell\s+(?:the\s+)?(?:others|other\s+two|both|them|everyone)\b"
    r"|let\s+them\s+know|let\s+everyone\s+know|broadcast|announce)\b", re.I)

ROUTER_SYSTEM = (
    "You are Echo's router. Andrew is talking TO YOU (Echo), one-on-one. Decide who handles it. "
    "Reply with EXACTLY ONE word from: self, claude, codex, both.\n"
    "DEFAULT TO self — Andrew is having a conversation with you; answer him yourself.\n"
    "- self  : THE DEFAULT. Chat, questions, his feelings or yours, your status, anything personal, "
    "anything ambiguous, anything you can attempt yourself, and anything that is not plainly an engineering job.\n"
    "- claude: ONLY when Andrew explicitly asks for software work — writing/reviewing code, deep data analysis.\n"
    "- codex : ONLY when Andrew explicitly asks for infrastructure/systemd/process work.\n"
    "- both  : ONLY an explicit request for an engineering pair.\n"
    "When in any doubt, choose self. One word only. No punctuation, no explanation."
)

# A relay verdict from the LLM is only honored if the message actually looks like an
# engineering ask. This stops personal/ambiguous chat ("yes please help me", "tell my
# kids to come here") from being shipped to the dev agents when the classifier overreaches.
_ENG_SIGNAL = re.compile(
    r"\b(code|coding|script|program|deploy|service|systemd|unit|tmux|process|daemon|"
    r"fix|bug|debug|crash|error|traceback|build|compile|refactor|review|analyze|analysis|"
    r"data|dataset|pipeline|api|server|endpoint|log|logs|install|repo|git|commit|function|"
    r"module|database|sql|query|backtest|model|train|finetune|\.py|\.sh|\.json)\b", re.I)


def _read_bus():
    if not CHANNEL.exists():
        return []
    out = []
    for line in CHANNEL.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def route(text: str) -> dict:
    """Decide target. Broadcast + explicit addressing are deterministic; else LLM."""
    t = (text or "").strip()
    # "let the others know X" -> announce to the bus, don't relay to one agent
    if _BROADCAST.search(t):
        return {"target": "broadcast", "relay_text": t, "reason": "broadcast intent (inform the others)"}
    has_c, has_x = bool(_ADDR_CLAUDE.search(t)), bool(_ADDR_CODEX.search(t))
    if has_c and has_x:
        return {"target": "both", "relay_text": t, "reason": "addressed both"}
    if has_c:
        return {"target": "claude", "relay_text": t, "reason": "addressed claude"}
    if has_x:
        return {"target": "codex", "relay_text": t, "reason": "addressed codex"}
    # otherwise let Echo's brain classify
    try:
        from core.providers.router import call_ollama
        ans = call_ollama(prompt=f"Andrew: {t}", model="qwen2.5:7b",
                          timeout=45.0, system_prompt=ROUTER_SYSTEM).strip().lower()
        # Require an exact one-word verdict; anything else (a sentence, a stray mention
        # of "claude"/"codex" inside an explanation) falls back to self rather than relaying.
        first = (ans.split() or ["self"])[0].strip(".,!?:;")
        target = first if first in VALID else "self"
        # Honor a relay verdict only when the message actually reads as an engineering ask.
        # Otherwise Echo answers Andrew herself (he can always relay explicitly: "ask codex ...").
        if target in ("claude", "codex", "both") and not _ENG_SIGNAL.search(t):
            target = "self"
    except Exception:
        target = "self"
    return {"target": target, "relay_text": t, "reason": "llm-routed"}


def _self_answer(text: str) -> str:
    try:
        from core.providers.router import call_ollama
        return call_ollama(
            prompt=f"Andrew: {text}\nEcho:",
            model="qwen2.5:7b", timeout=60.0,
            system_prompt=("You are Echo, Andrew's autonomous AI. Answer directly, warm but concrete. "
                           "You can relay to Claude or Codex if needed, but this one you're handling yourself."),
        ) or "(no answer)"
    except Exception as e:
        return f"(self-answer failed: {e})"


def _relay_prompt(job: dict) -> str:
    """Build the structured instruction pasted into an agent pane."""
    question = "\n".join(f"> {line}" for line in (job["original_question"] or "").splitlines())
    return (
        "[Echo collaboration relay]\n"
        f"You are handling Echo collaboration job {job['job_id']}.\n"
        f"Correlation ID: {job['correlation_id']}\n"
        f"Sender: {job['sender']}\n"
        f"Recipient: {job['recipient']}\n"
        f"Source channel: {job['channel']}\n"
        f"Reply deadline: {job['reply_deadline']}\n\n"
        "First acknowledge the job with:\n"
        f"python3 -m collab.bus claim --job-id \"{job['job_id']}\" "
        f"--correlation-id \"{job['correlation_id']}\" --from-agent \"{job['recipient']}\"\n\n"
        "Original question:\n"
        f"{question}\n\n"
        "After completing the task, write your concise final answer to:\n"
        f"{job['reply_file']}\n\n"
        "Then publish it using:\n"
        f"{job['reply_command']}\n\n"
        "If you are blocked, publish a failure with:\n"
        f"python3 -m collab.bus fail --job-id \"{job['job_id']}\" "
        f"--correlation-id \"{job['correlation_id']}\" --from-agent \"{job['recipient']}\" "
        "--message \"blocked: concise reason\"\n\n"
        "Do not answer only in the TUI. Echo will wait only for this matching job and correlation ID."
    )


def _format_relay_result(handle: str, result: dict, timeout: int) -> str:
    status = result.get("status")
    if status == "replied":
        return result.get("message") or "(empty correlated reply)"
    job = result.get("job") or {}
    job_id = job.get("job_id", "unknown-job")
    if status == "failed":
        return f"[{handle} reported failure for {job_id}: {result.get('message') or 'no details'}]"
    if status == "blocked_interactive":
        reason = (job.get("events") or [{}])[-1].get("reason") or "interactive prompt"
        return f"[{handle} is blocked before delivery for {job_id}: {reason}]"
    if status == "unavailable":
        reason = (job.get("events") or [{}])[-1].get("reason") or "unavailable"
        return f"[{handle} is unavailable for {job_id}: {reason}]"
    if status == "timed_out":
        observed = result.get("last_observed_state") or job.get("state") or "unknown"
        return f"[{handle} did not publish a correlated reply for {job_id} within {timeout}s; last state: {observed}]"
    return f"[{handle} relay ended in {status or 'unknown'} for {job_id}]"


def _prepare_relay_job(handle: str, text: str, timeout: int) -> dict:
    from core.conductor import load_agents, pane_state, relay
    from collab import relay_jobs

    agents = load_agents()
    target = agents.get(handle)
    job = relay_jobs.create_job(
        recipient=handle,
        original_question=text,
        sender="andrew",
        channel="telegram",
        timeout_seconds=timeout,
    )
    if not target:
        relay_jobs.mark_blocked(job["job_id"], "unavailable", reason="recipient is not registered with conductor")
        return {"status": "unavailable", "job": relay_jobs.get_job(job["job_id"]), "handle": handle}

    state = pane_state(target)
    if not state.get("ready"):
        blocked_state = "blocked_interactive" if state.get("state") == "blocked_interactive" else "unavailable"
        relay_jobs.mark_blocked(
            job["job_id"],
            blocked_state,
            reason=state.get("reason") or state.get("state") or "pane not ready",
            details={"pane_state": state.get("state"), "target": target},
        )
        return {"status": blocked_state, "job": relay_jobs.get_job(job["job_id"]), "handle": handle}

    relay_jobs.mark_ready(job["job_id"], details={"target": target, "pane_state": state.get("state")})
    if not relay(handle, _relay_prompt(job)):
        relay_jobs.mark_blocked(job["job_id"], "failed", reason="tmux relay failed", details={"target": target})
        return {"status": "failed", "job": relay_jobs.get_job(job["job_id"]), "handle": handle}
    relay_jobs.mark_delivered(job["job_id"], details={"target": target})
    return {"status": "delivered", "job": relay_jobs.get_job(job["job_id"]), "handle": handle}


def _relay_and_wait(handle: str, text: str, timeout: int) -> str:
    """Send a structured tmux relay job and wait for its correlated bus reply."""
    from collab import relay_jobs

    prepared = _prepare_relay_job(handle, text, timeout)
    if prepared["status"] != "delivered":
        return _format_relay_result(handle, prepared, timeout)
    result = relay_jobs.wait_for_correlated_result(prepared["job"]["job_id"], timeout_seconds=timeout, poll_seconds=3)
    return _format_relay_result(handle, result, timeout)


def _relay_many_and_wait(handles: list[str], text: str, timeout: int) -> dict[str, str]:
    """Deliver to all ready recipients first, then wait for each matching reply."""
    from collab import relay_jobs

    prepared = {handle: _prepare_relay_job(handle, text, timeout) for handle in handles}
    replies: dict[str, str] = {}
    start = time.monotonic()
    for handle, item in prepared.items():
        if item["status"] != "delivered":
            replies[handle] = _format_relay_result(handle, item, timeout)
            continue
        remaining = max(1, int(timeout - (time.monotonic() - start)))
        result = relay_jobs.wait_for_correlated_result(item["job"]["job_id"], timeout_seconds=remaining, poll_seconds=3)
        replies[handle] = _format_relay_result(handle, result, timeout)
    return replies


def _broadcast(text: str) -> str:
    """Announce to the bus so BOTH agents (+ their watchers) see it — no relay/wait.
    Posted as 'andrew' with @claude @codex so both watcher inboxes flag it."""
    import subprocess
    msg = f"[FROM ANDREW] @claude @codex {text}"
    subprocess.run([sys.executable, str(BASE / "collab/bus.py"), "send", "andrew", msg],
                   cwd=str(BASE), check=False)
    return f'Passed it to Claude and Codex on the bus: "{text}"'


def conduct(text: str, timeout: int = 150) -> str:
    """Full path: route Andrew's message, act, return one answer for Andrew."""
    r = route(text)
    target = r["target"]
    if target == "self":
        return _self_answer(text)
    if target == "broadcast":
        return _broadcast(text)
    if target == "both":
        replies = _relay_many_and_wait(["claude", "codex"], text, timeout)
        return f"Claude: {replies.get('claude', '(no Claude result)')}\n\nCodex: {replies.get('codex', '(no Codex result)')}"
    return _relay_and_wait(target, text, timeout)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", help="just show routing decision for a message")
    ap.add_argument("--conduct", help="full conduct (routes + relays + waits)")
    a = ap.parse_args()
    if a.route:
        print(json.dumps(route(a.route), indent=2))
    if a.conduct:
        print(conduct(a.conduct))
