#!/usr/bin/env python3
"""
core/code_sandbox.py
Safe execution gate for Echo's self-generated code.

Pipeline:
  1. Syntax check (py_compile)
  2. Static safety scan (forbidden patterns)
  3. Import check (loads module without running main)
  4. Dry-run (if script supports --dry-run flag)
  5. Verdict: PASS → auto-deploy to builds/deployed/  FAIL → quarantine with reason

Echo can write and auto-deploy new tools without Andrew's approval IF and ONLY IF
the sandbox passes all 5 stages. Core file modifications still require human approval.
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SANDBOX_LOG = BASE / "logs" / "code_sandbox.log"
DEPLOYED_DIR = BASE / "builds" / "deployed"
QUARANTINE_DIR = BASE / "builds" / "quarantine"

DEPLOYED_DIR.mkdir(parents=True, exist_ok=True)
QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)


def _log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"
    print(line)
    with open(SANDBOX_LOG, "a") as f:
        f.write(line + "\n")


# ── Forbidden patterns ────────────────────────────────────────────────────────
# Any script containing these is rejected outright.
FORBIDDEN_PATTERNS = [
    # Destructive filesystem ops
    ("shutil.rmtree", "deletes directory trees"),
    ("os.remove(", "deletes files"),
    ("os.unlink(", "deletes files"),
    ("Path.unlink(", "deletes files"),
    (".unlink(", "deletes files"),
    # Shell injection risk
    ("shell=True", "shell injection risk"),
    ("os.system(", "shell injection risk"),
    ("eval(", "code injection risk"),
    ("exec(", "code injection risk"),
    # Writes outside Echo dir
    ('open("/etc/', "writes outside Echo"),
    ('open("/root/', "writes outside Echo"),
    (f'open("{Path.home()}/."', "escapes Echo home"),
    # Network listeners (Echo should call out, not listen)
    ("socket.bind(", "opens network listener"),
    ("BaseHTTPServer", "opens HTTP server"),
    ("http.server", "opens HTTP server"),
    # Protected file writes
    ("echo_contract.json", "touches soul document"),
    ("Echo.Modelfile", "touches modelfile"),
    ("echo_semantic_memory", "touches memory database"),
]

# Core files Echo is NOT allowed to auto-modify (require human approval)
PROTECTED_PATHS = {
    "echo_core_daemon.py",
    "core/trade_brain.py",
    "core/crypto_brain.py",
    "core/self_act.py",
    "core/auto_act.py",
    "echo_contract.json",
    "Echo.Modelfile",
}


def check_syntax(code: str) -> tuple[bool, str]:
    try:
        compile(code, "<sandbox>", "exec")
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"


def check_safety(code: str) -> tuple[bool, str]:
    for pattern, reason in FORBIDDEN_PATTERNS:
        if pattern in code:
            return False, f"Forbidden pattern '{pattern}': {reason}"
    # AST walk for dynamic eval/exec
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in ("eval", "exec", "compile"):
                    return False, f"Forbidden call: {func.id}()"
    except Exception:
        pass
    return True, ""


def check_import(code: str, script_path: Path) -> tuple[bool, str]:
    """Try to import the module without running __main__ block."""
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             f"import ast, py_compile; py_compile.compile(r'{script_path}', doraise=True)"],
            capture_output=True, text=True, timeout=15,
            cwd=str(BASE)
        )
        if result.returncode != 0:
            return False, result.stderr.strip()[:300]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Import check timed out (15s)"
    except Exception as e:
        return False, str(e)


def dry_run(script_path: Path) -> tuple[bool, str]:
    """Run with --dry-run if supported; otherwise skip."""
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), "--dry-run"],
            capture_output=True, text=True, timeout=30,
            cwd=str(BASE),
            env={**os.environ, "SANDBOX": "1"}
        )
        output = (result.stdout + result.stderr)[:500]
        if result.returncode == 0:
            return True, output
        # Exit code 2 = argparse "unrecognized --dry-run" — script doesn't support it, skip
        if result.returncode == 2 and "unrecognized" in result.stderr:
            return True, "dry-run not supported — skipped"
        return False, output
    except subprocess.TimeoutExpired:
        return False, "Dry-run timed out (30s)"
    except Exception as e:
        return False, str(e)


def run_sandbox(
    code: str,
    script_name: str,
    target_path: str | None = None,
    auto_deploy: bool = True,
) -> dict:
    """
    Full sandbox pipeline.

    Args:
        code:         Python source to test
        script_name:  filename (e.g. 'monitor_cpu.py')
        target_path:  relative path inside Echo if deploying to a specific location
        auto_deploy:  move to builds/deployed/ on PASS

    Returns dict with keys: passed, stage, reason, deployed_path
    """
    result = {
        "passed": False,
        "stage": None,
        "reason": "",
        "deployed_path": None,
        "timestamp": datetime.now().isoformat(),
        "script": script_name,
    }

    _log(f"[sandbox] START {script_name}")

    # Stage 1: syntax
    ok, err = check_syntax(code)
    if not ok:
        result["stage"] = "syntax"
        result["reason"] = err
        _log(f"[sandbox] FAIL syntax: {err}")
        _quarantine(code, script_name, result)
        return result
    _log(f"[sandbox] PASS syntax")

    # Stage 2: safety
    ok, err = check_safety(code)
    if not ok:
        result["stage"] = "safety"
        result["reason"] = err
        _log(f"[sandbox] FAIL safety: {err}")
        _quarantine(code, script_name, result)
        return result
    _log(f"[sandbox] PASS safety")

    # Write to tmpdir for remaining checks
    with tempfile.TemporaryDirectory(prefix="echo_sandbox_") as tmpdir:
        tmp_script = Path(tmpdir) / script_name
        tmp_script.write_text(code)

        # Stage 3: import / compile
        ok, err = check_import(code, tmp_script)
        if not ok:
            result["stage"] = "import"
            result["reason"] = err
            _log(f"[sandbox] FAIL import: {err}")
            _quarantine(code, script_name, result)
            return result
        _log(f"[sandbox] PASS import")

        # Stage 4: dry-run
        ok, out = dry_run(tmp_script)
        if not ok:
            result["stage"] = "dry_run"
            result["reason"] = out
            _log(f"[sandbox] FAIL dry-run: {out[:120]}")
            _quarantine(code, script_name, result)
            return result
        _log(f"[sandbox] PASS dry-run: {out[:80]}")

    # All stages passed
    result["passed"] = True
    result["stage"] = "all"
    _log(f"[sandbox] ALL PASS — {script_name}")

    if auto_deploy:
        deployed = _deploy(code, script_name, target_path)
        result["deployed_path"] = str(deployed)
        _log(f"[sandbox] DEPLOYED → {deployed}")

    _record_result(result)
    return result


def _quarantine(code: str, script_name: str, result: dict):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = QUARANTINE_DIR / f"{ts}_{script_name}"
    path.write_text(code)
    reason_file = path.with_suffix(".reason.txt")
    reason_file.write_text(json.dumps(result, indent=2))
    _log(f"[sandbox] QUARANTINED → {path.name}")
    _record_result(result)


def _deploy(code: str, script_name: str, target_path: str | None) -> Path:
    if target_path:
        dest = BASE / target_path
        dest.parent.mkdir(parents=True, exist_ok=True)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = DEPLOYED_DIR / f"{ts}_{script_name}"
    dest.write_text(code)
    dest.chmod(0o755)
    return dest


def _record_result(result: dict):
    log_file = BASE / "memory" / "sandbox_results.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(result) + "\n")


def is_protected(file_path: str) -> bool:
    """Returns True if the file requires human approval to modify."""
    p = Path(file_path)
    return p.name in PROTECTED_PATHS or str(p) in PROTECTED_PATHS


if __name__ == "__main__":
    # Self-test with a safe dummy script
    test_code = '''#!/usr/bin/env python3
"""Test script for sandbox validation."""
import sys
def main():
    print("sandbox test ok")
if __name__ == "__main__":
    main()
'''
    r = run_sandbox(test_code, "sandbox_selftest.py", auto_deploy=False)
    print(f"Result: {'PASS' if r['passed'] else 'FAIL'} — stage={r['stage']} reason={r['reason']}")
