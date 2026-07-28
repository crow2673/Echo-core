#!/usr/bin/env python3
"""Ollama call router — single entry point for all LLM calls in Echo."""
import json
import os
from pathlib import Path
import urllib.request

BASE = Path(__file__).resolve().parents[2]
LOCAL_OPERATION_MODE = BASE / "memory/local_operation_mode.json"
LOCAL_ONLY_REASONING_MODEL = "qwen2.5:7b"


def local_only_mode_enabled() -> bool:
    if os.environ.get("ECHO_LOCAL_ONLY_MODE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    try:
        if LOCAL_OPERATION_MODE.exists():
            data = json.loads(LOCAL_OPERATION_MODE.read_text())
            return bool(data.get("enabled"))
    except Exception:
        return False
    return False


def _ollama_model_available(model: str, timeout: float = 5.0) -> bool:
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/tags",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        return any(item.get("name") == model for item in data.get("models", []))
    except Exception:
        return False


def select_ollama_model(requested_model: str | None = None, *, purpose: str = "reasoning") -> dict:
    """Return the model allowed by current operating policy."""
    requested = requested_model or LOCAL_ONLY_REASONING_MODEL
    if not local_only_mode_enabled():
        return {
            "model": requested,
            "requested_model": requested,
            "policy_source": "default",
            "allowed": True,
            "reason": "local-only mode disabled",
        }

    if not _ollama_model_available(LOCAL_ONLY_REASONING_MODEL):
        return {
            "model": "",
            "requested_model": requested,
            "policy_source": "memory/local_operation_mode.json",
            "allowed": False,
            "reason": f"local-model-unavailable: {LOCAL_ONLY_REASONING_MODEL}",
            "purpose": purpose,
        }

    if requested != LOCAL_ONLY_REASONING_MODEL:
        return {
            "model": LOCAL_ONLY_REASONING_MODEL,
            "requested_model": requested,
            "policy_source": "memory/local_operation_mode.json",
            "allowed": True,
            "reason": f"local-only mode remapped {requested} to {LOCAL_ONLY_REASONING_MODEL}",
            "purpose": purpose,
        }

    return {
        "model": requested,
        "requested_model": requested,
        "policy_source": "memory/local_operation_mode.json",
        "allowed": True,
        "reason": "local-only mode allowed reasoning model",
        "purpose": purpose,
    }


def call_ollama(
    prompt: str,
    model: str = "qwen2.5:7b",
    timeout: float = 120.0,
    system_prompt: str = "",
) -> str:
    """Call Ollama and return the response string, or '' on failure."""
    policy = select_ollama_model(model)
    if not policy.get("allowed"):
        print(f"[router] model policy blocked request: {policy['reason']}")
        return ""
    selected_model = str(policy["model"])
    if selected_model != model:
        print(
            "[router] model policy remapped request: "
            f"{model} -> {selected_model} ({policy['policy_source']})"
        )
    payload = {"model": selected_model, "stream": False, "options": {"num_predict": 2048}}
    if system_prompt:
        payload["system"] = system_prompt
    payload["prompt"] = prompt

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            result = json.loads(r.read())
            return result.get("response", "").strip()
    except Exception as e:
        print(f"[router] call_ollama error ({selected_model}): {e}")
        return ""
