#!/usr/bin/env python3
"""Agent loop — iterative Ollama reasoning with tool calls."""
from core.providers.router import call_ollama


def agent_loop(
    prompt: str,
    system_prompt: str = "",
    call_ollama_fn=None,
    model: str = "qwen2.5:7b",
    timeout: float = 180.0,
    max_iterations: int = 3,
    auto_approve_safe: bool = True,
) -> str:
    """Single-shot reasoning — no tool loop yet, falls back to direct call."""
    fn = call_ollama_fn or call_ollama
    return fn(prompt=prompt, model=model, timeout=timeout, system_prompt=system_prompt)
