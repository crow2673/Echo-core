#!/usr/bin/env python3
"""Tests for local-only Ollama model selection policy."""
from __future__ import annotations

import urllib.request

from core import dispatcher, gpt_reasoner
from core.providers import router


def test_local_only_remaps_llama_fallback_to_qwen(monkeypatch) -> None:
    monkeypatch.setattr(router, "local_only_mode_enabled", lambda: True)
    monkeypatch.setattr(router, "_ollama_model_available", lambda model, timeout=5.0: model == "qwen2.5:7b")

    policy = router.select_ollama_model("llama3.1:latest", purpose="self_act_fallback")

    assert policy["allowed"] is True
    assert policy["requested_model"] == "llama3.1:latest"
    assert policy["model"] == "qwen2.5:7b"
    assert policy["policy_source"] == "memory/local_operation_mode.json"


def test_missing_qwen_fails_closed_without_ollama_generate(monkeypatch) -> None:
    called_generate = False

    def fake_urlopen(*args, **kwargs):
        nonlocal called_generate
        called_generate = True
        raise AssertionError("generate endpoint should not be called when local model is unavailable")

    monkeypatch.setattr(router, "local_only_mode_enabled", lambda: True)
    monkeypatch.setattr(router, "_ollama_model_available", lambda model, timeout=5.0: False)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert router.call_ollama("hello", model="llama3.1:latest") == ""
    assert called_generate is False


def test_non_local_only_preserves_requested_model(monkeypatch) -> None:
    monkeypatch.setattr(router, "local_only_mode_enabled", lambda: False)

    policy = router.select_ollama_model("llama3.1:latest", purpose="normal_operation")

    assert policy["allowed"] is True
    assert policy["model"] == "llama3.1:latest"
    assert policy["policy_source"] == "default"


def test_gpt_reasoner_requests_qwen_default(monkeypatch) -> None:
    calls = []

    def fake_call_ollama(prompt, model=None, timeout=0, system_prompt=""):
        calls.append({"prompt": prompt, "model": model, "timeout": timeout, "system_prompt": system_prompt})
        return "ok"

    monkeypatch.setattr(gpt_reasoner, "call_ollama", fake_call_ollama)

    assert gpt_reasoner.gpt_reasoner("test prompt") == "ok"
    assert calls[0]["model"] == "qwen2.5:7b"


def test_dispatcher_judgment_requests_qwen_default(monkeypatch) -> None:
    calls = []

    def fake_call_ollama(prompt, model=None, timeout=0, system_prompt=""):
        calls.append({"prompt": prompt, "model": model, "timeout": timeout, "system_prompt": system_prompt})
        return "YES - fixture conditions are acceptable."

    monkeypatch.setattr(router, "call_ollama", fake_call_ollama)

    decision, reason = dispatcher.step4_echo_judgment(
        "fixture_worker",
        {"description": "fixture worker"},
        {"system_health": "OK", "system": {"cpu_pct": 10, "ram_pct": 40, "vram_total_mb": 12288, "vram_used_mb": 0}},
        {"summary": "fixture history"},
    )

    assert decision is True
    assert "YES" in reason
    assert calls[0]["model"] == "qwen2.5:7b"
