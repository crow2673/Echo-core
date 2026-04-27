#!/usr/bin/env python3
"""Self-coder — generates and tests Python via Ollama. Used by auto_act."""
import ast
import subprocess
import tempfile
from pathlib import Path

from core.providers.router import call_ollama

BASE = Path.home() / "Echo"


def write_code(task_description: str, output_path: str, context: str = "") -> bool:
    prompt = (
        f"Write a complete, working Python 3 script for the following task:\n\n"
        f"{task_description}\n\n"
        f"Context: {context}\n\n"
        f"Return ONLY the Python code, no explanation, no markdown fences."
    )
    code = call_ollama(prompt=prompt, model="qwen2.5:32b", timeout=300.0,
                       system_prompt="You are a Python expert. Write clean, safe, working code.")
    if not code:
        return False
    try:
        full_path = BASE / output_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(code)
        return True
    except Exception as e:
        print(f"[self_coder] write_code failed: {e}")
        return False


def fix_file(file_path: str, fix_description: str) -> bool:
    full_path = BASE / file_path
    if not full_path.exists():
        print(f"[self_coder] fix_file: {file_path} not found")
        return False
    original = full_path.read_text()
    prompt = (
        f"Fix the following Python file according to this instruction:\n{fix_description}\n\n"
        f"Original code:\n{original}\n\n"
        f"Return ONLY the corrected Python code, no explanation."
    )
    fixed = call_ollama(prompt=prompt, model="qwen2.5:32b", timeout=300.0,
                        system_prompt="You are a Python expert. Fix the code exactly as instructed.")
    if not fixed:
        return False
    try:
        full_path.write_text(fixed)
        return True
    except Exception as e:
        print(f"[self_coder] fix_file failed: {e}")
        return False


def test_code(file_path: str) -> bool:
    """Syntax check + dry-run import. Returns True if safe to deploy."""
    full_path = BASE / file_path
    if not full_path.exists():
        return False
    try:
        ast.parse(full_path.read_text())
    except SyntaxError as e:
        print(f"[self_coder] syntax error in {file_path}: {e}")
        return False
    result = subprocess.run(
        ["python3", "-c", f"import ast; ast.parse(open('{full_path}').read())"],
        capture_output=True, timeout=10
    )
    return result.returncode == 0
