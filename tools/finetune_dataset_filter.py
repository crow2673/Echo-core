#!/usr/bin/env python3
"""tools/finetune_dataset_filter.py — strip the poison from Echo's LoRA set.

finetune_dataset.jsonl captured every Telegram exchange UNLABELED, so Echo trained
on her corrected/hallucinated responses as hard as her good ones — an unfiltered
self-training loop that drifts (reinforces existing behavior, mistakes included).
This produces a CLEAN dataset to train the next adapter on.

Excludes (HARD-EXCLUDE policy — at 1.7% poison, down-weighting buys nothing):
  1. CORRECTED         — an Echo response whose NEXT human turn is a correction
                         ("that's wrong", "fabricated"): a confidently-wrong reply.
  2. CORRECTION_PROMPTED— the exchange whose human turn IS a correction (Echo's
                         reply to "you're wrong" is often flailing; don't learn it).
  3. MALFORMED         — Echo's own messages leaked into the human side, or empties.

Keeps everything else; reports the handful you explicitly praised (training gold).
Output: memory/finetune_dataset_clean.jsonl + a report.

Uses the SAME correction classifier as the interaction_ledger, so labels stay
consistent with what Andrew's live corrections produce going forward.
"""
import json, sys, re
from pathlib import Path
from datetime import datetime
from collections import Counter

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from core.interaction_ledger import classify, polarity

SRC = BASE / "memory/finetune_dataset.jsonl"
OUT = BASE / "memory/finetune_dataset_clean.jsonl"
REPORT = BASE / "memory/finetune_dataset_filter_report.json"

_ECHO_LEAK = re.compile(r"^\s*echo\s*[\[,]", re.I)  # "Echo, [date]" = Echo's own msg mislabeled human


def human(ex):
    for c in ex.get("conversations", []):
        if c.get("from") == "human":
            return c.get("value", "")
    return ""


def echo(ex):
    for c in ex.get("conversations", []):
        if c.get("from") == "gpt":
            return c.get("value", "")
    return ""


def _is_correction(text):
    return classify(text) == "correction" or polarity(text) < 0


def main():
    rows = []
    for line in SRC.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    rows.sort(key=lambda r: r.get("ts", ""))
    n = len(rows)

    reasons = {}  # idx -> exclude reason
    for i, ex in enumerate(rows):
        h, e = human(ex), echo(ex)
        if not h.strip() or not e.strip():
            reasons[i] = "malformed_empty"
            continue
        if _ECHO_LEAK.match(h):
            reasons[i] = "malformed_echo_as_human"
            continue
        if _is_correction(h):
            reasons[i] = "correction_prompted"
            continue
        if i + 1 < n and _is_correction(human(rows[i + 1])):
            reasons[i] = "corrected_response"
            continue

    kept = [ex for i, ex in enumerate(rows) if i not in reasons]
    praised = [i for i in range(n - 1)
               if polarity(human(rows[i + 1])) > 0 and i not in reasons]

    OUT.write_text("\n".join(json.dumps(ex) for ex in kept) + "\n")
    report = {
        "generated_at": datetime.now().isoformat(),
        "policy": "hard-exclude",
        "source_examples": n,
        "kept": len(kept),
        "excluded": len(reasons),
        "exclude_breakdown": dict(Counter(reasons.values())),
        "praised_kept": len(praised),
        "output": str(OUT.relative_to(BASE)),
        "note": "Removes the KNOWN-bad (labeled corrections + leaks). The rest is "
                "unvalidated — clean != good. Train the next adapter on this file.",
    }
    REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
