from __future__ import annotations

import requests


class OllamaModel:
    """Local LLM adapter.

    The model is part of the AI installation at runtime. Ollama is only
    the local inference engine; the AI owns the identity, memory, tools,
    and self-improvement loop around it.
    """

    def __init__(self, model: str = "qwen2.5:7b", host: str = "http://127.0.0.1:11434"):
        self.model = model
        self.host = host.rstrip("/")

    def generate(self, prompt: str) -> str:
        response = requests.post(
            f"{self.host}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=300,
        )
        response.raise_for_status()
        return response.json()["response"]
