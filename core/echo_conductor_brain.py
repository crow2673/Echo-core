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


def _relay_and_wait(handle: str, text: str, timeout: int) -> str:
    """Type into the agent's tmux pane and wait for their next bus reply."""
    from core.conductor import relay, load_agents
    if handle not in load_agents():
        return (f"[{handle} isn't registered with the conductor yet — its tmux pane "
                f"needs to be launched + registered. Falling back: not relayed.]")
    baseline = _read_bus()
    last_id = baseline[-1]["id"] if baseline else 0
    # prefix so the woken agent knows it's a relayed request from Andrew via Echo
    framed = f"[via Echo from Andrew] {text}"
    if not relay(handle, framed):
        return f"[failed to type into {handle}'s pane]"
    # watch the bus for that agent's reply
    waited = 0
    while waited < timeout:
        time.sleep(3)
        waited += 3
        for m in _read_bus():
            if m["id"] > last_id and m["from"] == handle:
                return m["text"]
    return f"[{handle} was woken but hasn't replied on the bus within {timeout}s]"


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
        c = _relay_and_wait("claude", text, timeout)
        x = _relay_and_wait("codex", text, timeout)
        return f"Claude: {c}\n\nCodex: {x}"
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
