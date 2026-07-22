#!/usr/bin/env python3
"""
core/assimilator.py — Echo's skill acquisition engine.

Given a library name or GitHub URL, Echo:
  1. Researches what it does (pip info + README fetch)
  2. Compares against known_gaps.md to find what it fills
  3. Uses LLM to decide what specific piece to integrate
  4. Writes an integration wrapper into tools/
  5. Runs it through code_sandbox for safety
  6. Notifies Andrew via Telegram with a summary and proposed diff

Echo absorbs external tools like a human learning from others' code.
She takes the useful part — not the whole thing.
"""
import json
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

LOG = BASE / "logs/assimilator.log"
GAPS_FILE = BASE / "memory/known_gaps.md"
ASSIMILATED_FILE = BASE / "memory/assimilated_libraries.json"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[assimilator] {msg}", flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def _load_assimilated() -> dict:
    if ASSIMILATED_FILE.exists():
        try:
            return json.loads(ASSIMILATED_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_assimilated(data: dict):
    tmp = ASSIMILATED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(ASSIMILATED_FILE)


def _load_known_gaps() -> str:
    if GAPS_FILE.exists():
        return GAPS_FILE.read_text()
    return ""


def get_pypi_info(package_name: str) -> dict:
    """Fetch package metadata from PyPI."""
    try:
        url = f"https://pypi.org/pypi/{package_name}/json"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        info = data.get("info", {})
        return {
            "name": info.get("name", package_name),
            "summary": info.get("summary", ""),
            "description": info.get("description", "")[:2000],
            "home_page": info.get("home_page", ""),
            "version": info.get("version", ""),
        }
    except Exception as e:
        log(f"PyPI lookup failed for {package_name}: {e}")
        return {"name": package_name, "summary": "", "description": "", "home_page": "", "version": ""}


def evaluate_library(package_name: str, pypi_info: dict, gaps: str) -> dict:
    """Use LLM to evaluate whether and how to integrate this library."""
    from core.providers.router import call_ollama

    prompt = (
        f"You are Echo's assimilation engine. Evaluate whether to integrate this Python library.\n\n"
        f"LIBRARY: {pypi_info['name']} v{pypi_info['version']}\n"
        f"SUMMARY: {pypi_info['summary']}\n"
        f"DESCRIPTION:\n{pypi_info['description'][:1000]}\n\n"
        f"ECHO'S KNOWN GAPS:\n{gaps[:2000]}\n\n"
        f"ECHO'S PURPOSE: Autonomous AI assistant for Andrew. Income streams: crypto trading, "
        f"Fiverr automation, content generation. Runs locally on Ubuntu with 32GB RAM, RTX 3060.\n\n"
        f"Answer in JSON:\n"
        f"{{\n"
        f'  "should_integrate": true/false,\n'
        f'  "relevance_score": 0-10,\n'
        f'  "gap_it_fills": "which specific gap from known_gaps.md",\n'
        f'  "what_to_use": "specific feature or function to extract, not the whole library",\n'
        f'  "integration_idea": "one sentence on how Echo would use this",\n'
        f'  "risk": "low/medium/high — any concerns about adding this dependency"\n'
        f"}}\n\nJSON only, no other text:"
    )

    response = call_ollama(prompt, model="llama3.1:latest", timeout=90)

    try:
        # Extract JSON from response
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(response[start:end])
    except Exception:
        pass

    return {
        "should_integrate": False,
        "relevance_score": 0,
        "gap_it_fills": "unknown",
        "what_to_use": "",
        "integration_idea": "",
        "risk": "unknown",
    }


def write_integration_wrapper(package_name: str, evaluation: dict) -> Path | None:
    """Use LLM to write an integration wrapper for Echo."""
    from core.providers.router import call_ollama

    what_to_use = evaluation.get("what_to_use", "")
    integration_idea = evaluation.get("integration_idea", "")

    if not what_to_use or not integration_idea:
        return None

    prompt = (
        f"Write a Python integration wrapper for Echo's tools/ directory.\n\n"
        f"Library: {package_name}\n"
        f"What to use: {what_to_use}\n"
        f"How Echo uses it: {integration_idea}\n\n"
        f"Requirements:\n"
        f"- File goes in /home/andrew/Echo/tools/\n"
        f"- Must have a run() function as entry point\n"
        f"- Must import safely (try/except on the library import)\n"
        f"- Must log to /home/andrew/Echo/logs/ using standard log pattern\n"
        f"- Must be self-contained and useful to Echo immediately\n"
        f"- Do NOT import echo internals — keep it standalone\n"
        f"- Under 80 lines\n\n"
        f"Write ONLY the Python code, no explanation:"
    )

    code = call_ollama(prompt, model="qwen2.5:32b", timeout=180)

    # Strip markdown code blocks if present
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0].strip()
    elif "```" in code:
        code = code.split("```")[1].split("```")[0].strip()

    if not code or len(code) < 50:
        return None

    safe_name = package_name.replace("-", "_").replace(".", "_").lower()
    out_path = BASE / f"tools/assimilated_{safe_name}.py"
    out_path.write_text(code)
    log(f"Wrote integration wrapper: {out_path.name}")
    return out_path


def sandbox_test(file_path: Path) -> tuple[bool, str]:
    """Run the generated file through Echo's code sandbox."""
    try:
        from core.code_sandbox import sandbox_test_file
        ok, output = sandbox_test_file(str(file_path))
        return ok, output
    except ImportError:
        # Fallback: just syntax check
        try:
            result = subprocess.run(
                ["python3", "-c", f"compile(open('{file_path}').read(), '<test>', 'exec')"],
                capture_output=True, text=True, timeout=10
            )
            ok = result.returncode == 0
            return ok, result.stderr if not ok else "syntax OK"
        except Exception as e:
            return False, str(e)


def assimilate(package_name: str) -> dict:
    """
    Main entry point. Evaluate and optionally integrate a library into Echo.
    Returns a summary dict.
    """
    log(f"Assimilating: {package_name}")

    assimilated = _load_assimilated()
    if package_name in assimilated:
        log(f"Already processed {package_name} — skipping")
        return assimilated[package_name]

    pypi_info = get_pypi_info(package_name)
    gaps = _load_known_gaps()

    log(f"Evaluating {package_name}: {pypi_info['summary'][:60]}")
    evaluation = evaluate_library(package_name, pypi_info, gaps)

    log(f"Relevance score: {evaluation.get('relevance_score', 0)}/10 | "
        f"Integrate: {evaluation.get('should_integrate', False)}")

    result = {
        "package": package_name,
        "evaluated_at": datetime.now().isoformat(),
        "pypi_summary": pypi_info["summary"],
        "evaluation": evaluation,
        "wrapper_path": None,
        "sandbox_ok": None,
        "status": "evaluated",
    }

    if evaluation.get("should_integrate") and evaluation.get("relevance_score", 0) >= 6:
        wrapper = write_integration_wrapper(package_name, evaluation)
        if wrapper:
            sandbox_ok, sandbox_output = sandbox_test(wrapper)
            result["wrapper_path"] = str(wrapper)
            result["sandbox_ok"] = sandbox_ok
            result["status"] = "integrated" if sandbox_ok else "sandbox_failed"
            log(f"Sandbox: {'OK' if sandbox_ok else 'FAILED'} — {sandbox_output[:80]}")

            if not sandbox_ok:
                wrapper.unlink(missing_ok=True)
                result["wrapper_path"] = None
    else:
        result["status"] = "skipped"

    assimilated[package_name] = result
    _save_assimilated(assimilated)

    # Notify Andrew
    try:
        from core.notifier import notify as notify_telegram
        score = evaluation.get("relevance_score", 0)
        integrated = result["status"] == "integrated"
        gap = evaluation.get("gap_it_fills", "unknown")
        idea = evaluation.get("integration_idea", "")
        emoji = "✅" if integrated else ("⚠️" if score >= 4 else "❌")
        msg = (
            f"{emoji} Assimilation Report: {package_name}\n\n"
            f"Score: {score}/10\n"
            f"Gap filled: {gap}\n"
            f"Use: {idea}\n"
            f"Status: {result['status']}\n"
        )
        if result["wrapper_path"]:
            msg += f"Wrapper: tools/{Path(result['wrapper_path']).name}"
        notify_telegram("Echo Assimilation", msg)
    except Exception as e:
        log(f"Telegram notify failed: {e}")

    return result


if __name__ == "__main__":
    pkg = sys.argv[1] if len(sys.argv) > 1 else "schedule"
    result = assimilate(pkg)
    print(json.dumps(result, indent=2))
