#!/usr/bin/env python3
"""Shared rules for proving outcomes instead of merely observing activity."""


def context_block() -> str:
    return (
        "VERIFICATION CONTRACT:\n"
        "- Define the exact success criterion before claiming completion.\n"
        "- Any safe method is allowed; verification judges outcomes, not whether a prescribed method was used.\n"
        "- Novel methods are welcome when their resulting state satisfies independently checked invariants.\n"
        "- Evidence that something changed is not evidence that it changed correctly.\n"
        "- Hash differences, exit code 0, deployment, or activity logs alone do not prove correctness.\n"
        "- Verify important outputs with an independent oracle, deterministic invariant, or external result.\n"
        "- Include negative tests and preservation checks where relevant.\n"
        "- Prefer current live evidence over historical memory when they conflict.\n"
        "- Never say you are checking, running, reading, or doing something unless this response path "
        "actually performed it and has the result. Otherwise state the exact next check without implying it ran."
    )
