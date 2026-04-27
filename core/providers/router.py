#!/usr/bin/env python3
"""Ollama call router — single entry point for all LLM calls in Echo."""
import json
import urllib.request


def call_ollama(
    prompt: str,
    model: str = "qwen2.5:7b",
    timeout: float = 120.0,
    system_prompt: str = "",
) -> str:
    """Call Ollama and return the response string, or '' on failure."""
    payload = {"model": model, "stream": False, "options": {"num_predict": 2048}}
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
        print(f"[router] call_ollama error ({model}): {e}")
        return ""
