#!/usr/bin/env python3
"""
core/self_coder.py
Echo's self-coding engine.
Given a task description, Echo writes and saves Python code.
"""
import json
import subprocess
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]

def call_ollama(prompt, model="echo", timeout=600):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    import urllib.request
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            return result.get("message", {}).get("content", "")
    except Exception as e:
        return f"error: {e}"

def extract_code(text):
    """Extract Python code from model response."""
    if "```python" in text:
        start = text.find("```python") + 9
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()
    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()
    # If no code blocks, assume entire response is code
    if text.strip().startswith("#!/usr/bin/env python") or text.strip().startswith("import "):
        return text.strip()
    return None

def write_code(task_description, output_path, context=""):
    """Ask Echo to write code for a task and save it."""
    prompt = f"""You are Echo, an autonomous AI system. Write a complete, working Python script for this task:

TASK: {task_description}

CONTEXT:
{context}

Rules:
- Write ONLY the Python code, wrapped in ```python blocks
- No explanation before or after the code block
- The code must be complete and runnable
- Include error handling
- Add a brief docstring at the top
- The file will be saved to: {output_path}
"""
    print(f"[self_coder] Writing: {output_path}")
    print(f"[self_coder] Task: {task_description[:80]}...")
    
    response = call_ollama(prompt, model="echo", timeout=600)
    code = extract_code(response)
    
    if not code:
        print("[self_coder] No code extracted from response")
        print(f"[self_coder] Response preview: {response[:200]}")
        return False
    
    # Safety check
    target = (BASE / output_path).resolve()
    if not str(target).startswith(str(BASE)):
        print(f"[self_coder] DENIED: {target} outside Echo directory")
        return False
    
    # Backup if exists
    if target.exists():
        backup = target.with_suffix(".py.bak")
        backup.write_text(target.read_text())
        print(f"[self_coder] Backed up to {backup.name}")
    
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code)
    print(f"[self_coder] Written: {target} ({len(code)} chars)")
    
    # Log to changelog
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n## {timestamp} — Self-Coded: {output_path}\n- Task: {task_description[:100]}\n- Lines: {len(code.splitlines())}\n"
    with open(BASE / "CHANGELOG.md", "a") as f:
        f.write(entry)
    
    return True


def fix_file(file_path, fix_description):
    """Read an existing file, fix it based on description, overwrite it."""
    from datetime import datetime
    ftarget = (BASE / file_path).resolve()
    if not ftarget.exists():
        print(f"[self_coder] File not found: {file_path}")
        return False
    if not str(ftarget).startswith(str(BASE)):
        print(f"[self_coder] DENIED: {ftarget} outside Echo directory")
        return False
    existing_code = ftarget.read_text()
    prompt = (
        "You are Echo, an autonomous AI system. Fix the following Python file.\n\n"
        f"FILE: {file_path}\n"
        f"FIX NEEDED: {fix_description}\n\n"
        "CURRENT CODE:\n```python\n"
        f"{existing_code}\n```\n\n"
        "Rules:\n"
        "- Return ONLY the complete fixed Python code wrapped in ```python blocks\n"
        "- Do not explain anything before or after the code block\n"
        "- Keep everything that works, only fix what is broken\n"
        "- Include error handling\n"
    )
    print(f"[self_coder] Fixing: {file_path}")
    print(f"[self_coder] Fix: {fix_description[:80]}...")
    response = call_ollama(prompt, model="echo", timeout=600)
    code = extract_code(response)
    if not code:
        print("[self_coder] No code extracted from response")
        return False
    backup = ftarget.with_suffix(".py.bak")
    backup.write_text(existing_code)
    print(f"[self_coder] Backed up to {backup.name}")
    ftarget.write_text(code)
    print(f"[self_coder] Fixed: {ftarget} ({len(code)} chars)")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n## {timestamp} — Self-Fixed: {file_path}\n- Fix: {fix_description[:100]}\n"
    with open(BASE / "CHANGELOG.md", "a") as f:
        f.write(entry)
    return True


def test_code(file_path):
    """Syntax check the written code."""
    target = BASE / file_path
    result = subprocess.run(
        ["python3", "-m", "py_compile", str(target)],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"[self_coder] Syntax OK: {file_path}")
        return True
    else:
        print(f"[self_coder] Syntax ERROR: {result.stderr}")
        return False

if __name__ == "__main__":
    # Test: write the golem task matcher
    changelog = (BASE / "CHANGELOG.md").read_text()[-2000:]
    
    success = write_code(
        task_description="Check Golem provider status using ya-provider commands, identify why tasks=0, and log specific actionable recommendations to logs/golem_recommendations.log with timestamps. Run as a standalone script.",
        output_path="core/golem_task_matcher.py",
        context=f"Recent changelog:\n{changelog}"
    )
    
    if success:
        test_code("core/golem_task_matcher.py")
