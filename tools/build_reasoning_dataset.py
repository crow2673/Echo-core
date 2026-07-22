#!/usr/bin/env python3
"""tools/build_reasoning_dataset.py — turn verified reasoning traces into training data.

Converts memory/reasoning_traces.jsonl (VERIFIED task completions captured by
reasoning_trace_collector) into ShareGPT training format the LoRA pipeline reads.
Each example teaches: given THIS task, here is a reasoning+tool path that was
INDEPENDENTLY VERIFIED to produce the correct result. That's intelligence
training (correct task-solving), not voice training (chat transcripts).

Output: memory/reasoning_dataset.jsonl
Needs MIN_TRACES before the fine-tune should switch to it (a tiny corpus would
just overfit a handful of tasks).
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
TRACES = BASE / "memory/reasoning_traces.jsonl"
OUT = BASE / "memory/reasoning_dataset.jsonl"
MIN_TRACES = 50   # don't train on reasoning until the corpus is real


def _render(trace: dict) -> str:
    """A correct reasoning narrative from the verified steps + answer."""
    lines = ["Let me work through this with verification, not guesswork."]
    for i, s in enumerate(trace.get("steps", []), 1):
        tool = s.get("tool", "?")
        args = s.get("args", {})
        target = (args or {}).get("path") or (args or {}).get("query") or ""
        lines.append(f"{i}. {tool}({target}) — ok={s.get('ok')}")
    fa = trace.get("final_answer", "").strip()
    if fa:
        lines.append(f"Verified result: {fa}")
    lines.append("(outcome independently verified before claiming completion)")
    return "\n".join(lines)


def main():
    if not TRACES.exists():
        OUT.write_text("")
        print(f"no traces yet at {TRACES} — corpus empty (need {MIN_TRACES} to train). "
              f"Verified traces accumulate as Echo completes tasks.")
        return
    traces = [json.loads(l) for l in TRACES.read_text().splitlines() if l.strip()]
    examples = []
    for t in traces:
        if not t.get("verified"):
            continue
        examples.append({"conversations": [
            {"from": "human", "value": t.get("task", "")},
            {"from": "gpt", "value": _render(t)},
        ], "ts": t.get("ts"), "source": "verified_reasoning"})
    OUT.write_text("\n".join(json.dumps(e) for e in examples) + ("\n" if examples else ""))
    enough = len(examples) >= MIN_TRACES
    print(json.dumps({
        "verified_traces": len(examples),
        "min_to_train": MIN_TRACES,
        "ready_for_training": enough,
        "output": str(OUT.relative_to(BASE)),
        "note": ("ready — fine-tune will prefer this reasoning corpus"
                 if enough else
                 f"accumulating — {MIN_TRACES - len(examples)} more verified tasks needed; "
                 "fine-tune stays on filtered chat data until then"),
    }, indent=2))


if __name__ == "__main__":
    main()
