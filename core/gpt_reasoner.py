#!/usr/bin/env python3
"""Fallback reasoner — simple Ollama call when agent_loop is unavailable."""
from core.providers.router import call_ollama


def gpt_reasoner(prompt, core_state: dict = None) -> str:
    system = (
        "You are Echo, an autonomous AI agent. "
        "You are running a background reasoning cycle. "
        "Be concrete and specific. State what you found or decided."
    )
    return call_ollama(
        prompt=str(prompt),
        model="qwen2.5:7b",
        timeout=120.0,
        system_prompt=system,
    )
