#!/usr/bin/env python3
"""
Semantic action matcher for Echo's governor.
Uses all-MiniLM-L6-v2 embeddings to match reasoning text to actions
instead of brittle keyword matching.

Each action in actions.json gets a set of example phrases.
At match time, cosine similarity finds the best action.
Threshold: 0.45 — below that, no match (avoids false positives).
"""
import json, numpy as np
from pathlib import Path
from functools import lru_cache

BASE = Path(__file__).resolve().parents[1]
ACTIONS_FILE = BASE / "docs/actions.json"
THRESHOLD = 0.45

# Example phrases per action_id — what reasoning looks like when this action is needed
ACTION_EXAMPLES = {
    "golem_status": [
        "check golem node status",
        "golem provider running",
        "check if golem is earning",
        "golem node health",
        "verify golem is active",
        "golem uptime check",
        "is golem online",
        "golem service status",
    ],
    "golem_pricing_update": [
        "lower golem price",
        "reduce pricing to attract tasks",
        "golem pricing too high",
        "adjust golem cpu price",
        "drop golem duration price",
        "pricing adjustment needed",
    ],
    "healthcheck": [
        "check all services running",
        "system health check",
        "verify services are active",
        "registry verification",
        "check echo system state",
        "summarize current echo state",
        "which services are down",
        "read registry and verify",
    ],
    "query_ledger": [
        "summarize recent wins and losses",
        "query the event ledger",
        "what has echo done recently",
        "review recent actions",
        "check ledger for patterns",
        "todo review highest value action",
        "suggest next action from todo",
    ],
    "notify_phone": [
        "notify andrew",
        "alert andrew about issue",
        "send phone notification",
        "message andrew",
    ],
    "devto_publish": [
        "publish article to dev.to",
        "post article",
        "publish draft",
        "push content to devto",
    ],
    "create_draft": [
        "write article draft",
        "create new article",
        "world context trending topic",
        "identify article topic from trending",
        "queue article draft",
        "write about trending topic",
    ],
    "article_pipeline": [
        "run article pipeline",
        "write and review article",
        "pending review article",
        "draft ready for approval",
        "autonomous article",
    ],
    "golem_diagnostic": [
        "run golem diagnostic",
        "golem task matcher",
        "why is golem not getting tasks",
        "debug golem provider",
    ],
    "vast_status": [
        "check vast.ai status",
        "vast machine 57470",
        "gpu rental status",
        "any active rentals",
        "vast earnings",
        "vast.ai machine listed",
        "vast ai rentals",
    ],
    "read_income_knowledge": [
        "which income path to activate",
        "read income knowledge",
        "income path reasoning",
        "which income stream next",
        "passive income status",
        "income_knowledge.md",
        "activate next income",
    ],
    "read_todo": [
        "review todo.md",
        "highest value next action",
        "what should echo do next",
        "todo list review",
        "suggest next action",
    ],
    "read_registry": [
        "read registry.json",
        "verify all services running",
        "check registry",
        "services listed in registry",
    ],
}

@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer('all-MiniLM-L6-v2')

@lru_cache(maxsize=1)
def get_action_embeddings():
    """Pre-compute embeddings for all action examples."""
    model = get_model()
    action_vecs = {}
    for action_id, examples in ACTION_EXAMPLES.items():
        vecs = model.encode(examples)
        action_vecs[action_id] = vecs
    return action_vecs

def cosine_sim(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

def match(reasoning_text, actions):
    """
    Match reasoning_text to best action using semantic similarity.
    Returns (action, env_vars) or (None, None).
    """
    model = get_model()
    action_vecs = get_action_embeddings()

    query_vec = model.encode([reasoning_text])[0]

    best_score = 0.0
    best_action_id = None

    for action_id, vecs in action_vecs.items():
        # Score = max similarity across all examples for this action
        sims = [cosine_sim(query_vec, v) for v in vecs]
        score = max(sims)
        if score > best_score:
            best_score = score
            best_action_id = action_id

    if best_score < THRESHOLD:
        return None, None, best_score

    # Find action object
    if isinstance(actions, dict): actions = actions.get("actions", [])
    action = next((a for a in actions if a["id"] == best_action_id), None)
    if not action:
        return None, None, best_score

    # Build env_vars
    env_vars = {}
    if best_action_id == "golem_pricing_update":
        env_vars = {"GOLEM_CPU": "0.00008", "GOLEM_DUR": "0.00002"}
    elif best_action_id == "notify_phone":
        env_vars = {"ECHO_TITLE": "Echo Update", "ECHO_MSG": reasoning_text[:100]}

    return action, env_vars, best_score

if __name__ == "__main__":
    # Test
    tests = [
        "read memory/income_knowledge.md and reason about which income path to activate next",
        "check Golem node status and suggest pricing adjustment if needed",
        "review TODO.md and suggest the single highest-value next action",
        "summarize: current Echo system state in ONE paragraph",
        "check Vast.ai machine 57470 status — is it listed, any active rentals, earnings so far",
        "query_ledger: summarize recent wins and losses from the event ledger",
        "read registry.json and verify all listed services are actually running",
        "read memory/world_context.md and identify one trending topic Echo should write an article about",
    ]
    actions = json.loads(ACTIONS_FILE.read_text()).get("actions", [])
    print(f"Testing {len(tests)} standing tasks:\n")
    matched = 0
    for t in tests:
        action, env_vars, score = match(t, actions)
        status = f"→ {action['id']} (score={score:.3f})" if action else f"→ NO MATCH (score={score:.3f})"
        print(f"  {status}")
        print(f"    '{t[:70]}'")
        if action:
            matched += 1
    print(f"\n{matched}/{len(tests)} matched")
