#!/usr/bin/env python3
"""
Echo article reviewer — self-review pipeline.
Checks draft against quality checklist before queuing for human approval.
Runs after draft_writer produces a draft.
Returns (passed, issues, suggestions) tuple.
"""
import re, sys, json
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/article_reviewer.log"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

CHECKLIST = {
    "no_third_person_andrew": {
        "desc": "No third-person references to Andrew",
        "check": lambda t: "andrew" not in t.lower() or "by andrew" in t.lower()[:200],
        "fix": "rewrite using first person 'I' instead of 'Andrew'"
    },
    "first_person_voice": {
        "desc": "Uses first person voice",
        "check": lambda t: any(w in t.lower() for w in [" i ", " i'", "i've", "i'm", "my ", "we "]),
        "fix": "add first-person perspective — reader needs a human voice"
    },
    "no_duplicate_h1": {
        "desc": "H1 title not duplicated as H2",
        "check": lambda t: _no_duplicate_heading(t),
        "fix": "remove duplicate heading at top of article"
    },
    "no_log_file_bullets": {
        "desc": "No log file paths in bullets",
        "check": lambda t: "logs/" not in t and ".log" not in t,
        "fix": "remove log file references — not useful to readers"
    },
    "complete_article": {
        "desc": "Article has a conclusion",
        "check": lambda t: any(w in t.lower() for w in ["conclusion", "summary", "final", "wrap", "closing", "together", "result"]),
        "fix": "add a conclusion section"
    },
    "minimum_length": {
        "desc": "At least 400 words",
        "check": lambda t: len(t.split()) >= 400,
        "fix": "expand article — too short for dev.to audience"
    },
    "maximum_length": {
        "desc": "Under 1500 words",
        "check": lambda t: len(t.split()) <= 1500,
        "fix": "trim article — too long, aim for 800-1200 words"
    },
    "has_code_or_practical": {
        "desc": "Contains code block or practical steps",
        "check": lambda t: "```" in t or "step" in t.lower() or "install" in t.lower() or "run" in t.lower(),
        "fix": "add a code example or practical how-to steps"
    },
    "dev_audience": {
        "desc": "Relevant to developers",
        "check": lambda t: any(w in t.lower() for w in ["linux", "python", "code", "terminal", "install", "build", "deploy", "ai", "model", "script"]),
        "fix": "ensure content is relevant to developer audience"
    },
}

def _no_duplicate_heading(text):
    lines = text.strip().split("\n")
    h1 = None
    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            h1 = line[2:].strip().lower()
            break
    if not h1:
        return True
    for line in lines:
        if line.startswith("## "):
            h2 = line[3:].strip().lower()
            if h2 == h1:
                return False
    return True

def review(text):
    """
    Review article text against quality checklist.
    Returns (passed, issues, score) where score is 0.0-1.0.
    """
    issues = []
    fixes = []
    passed_count = 0

    for key, check in CHECKLIST.items():
        try:
            result = check["check"](text)
        except Exception:
            result = False
        if result:
            passed_count += 1
        else:
            issues.append(check["desc"])
            fixes.append(check["fix"])

    score = passed_count / len(CHECKLIST)
    passed = score >= 0.8  # 80% threshold to pass

    return passed, issues, fixes, score

def review_file(path):
    """Review a draft file. Returns (passed, issues, fixes, score)."""
    text = Path(path).read_text()
    passed, issues, fixes, score = review(text)

    log(f"reviewing: {Path(path).name}")
    log(f"  score: {score:.0%} ({len(CHECKLIST)-len(issues)}/{len(CHECKLIST)} checks passed)")

    if issues:
        log(f"  issues:")
        for i, (issue, fix) in enumerate(zip(issues, fixes)):
            log(f"    [{i+1}] FAIL: {issue}")
            log(f"         FIX: {fix}")
    else:
        log("  all checks passed")

    return passed, issues, fixes, score

if __name__ == "__main__":
    # Test on the bad article
    path = BASE / "content/article_20260311_211941.md"
    if path.exists():
        passed, issues, fixes, score = review_file(path)
        print(f"\nVerdict: {'PASS' if passed else 'FAIL'} ({score:.0%})")
    else:
        print("test article not found")
