#!/usr/bin/env python3
"""Semantic matcher — matches reasoning text to actions using sentence-transformers."""
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer, util
    _model = SentenceTransformer("all-MiniLM-L6-v2")
    AVAILABLE = True
except Exception:
    AVAILABLE = False


def match(reasoning_text: str, actions: list, threshold: float = 0.45):
    """
    Match reasoning_text to the best action using cosine similarity.
    Returns (action, env_vars, score) or (None, None, 0.0).
    """
    if not AVAILABLE or not actions:
        return None, None, 0.0

    descriptions = [a.get("description", a.get("id", "")) for a in actions]
    try:
        q_emb = _model.encode(reasoning_text, convert_to_tensor=True)
        a_embs = _model.encode(descriptions, convert_to_tensor=True)
        scores = util.cos_sim(q_emb, a_embs)[0]
        best_idx = int(scores.argmax())
        best_score = float(scores[best_idx])
        if best_score >= threshold:
            return actions[best_idx], {}, best_score
    except Exception as e:
        print(f"[semantic_matcher] error: {e}")
    return None, None, 0.0
