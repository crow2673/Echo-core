#!/usr/bin/env python3
"""
Echo AGI Lite (Clean)
Focus: AI/agent/vision/memory/spy only.
Loop: scan (e_scan.sh) -> GAI (ollama) -> safe_act (read-only) -> log + memory.

- No installs
- No network/ports actions
- No finance/golem keywords/actions
"""

import os
import json
import time
import subprocess
import datetime
from typing import Dict, Any, List, Optional

MODEL = "gai"  # ollama model name
SCAN_CMD = ["bash", "-lc", "./e_scan.sh"]
LOG_FILE = "echo_activity.log"
STATE_FILE = "echo_agi_state.json"
MEM_FILE = "echo_memory_ai.json"

# Vision is optional: it will use newest screen_*.png if present (no capture needed)
VISION_GLOB_PREFIX = "screen_"
VISION_LATEST_FALLBACK = "screen_latest.png"  # if you manually create it
ENABLE_VISION_OCR = False  # set True only after screenshot pipeline works

SAFE_PREFIXES = (
    "cat ", "tail ", "ls ", "grep ", "sed -n ", "awk ", "head ", "du ", "df ",
    "ps ", "pgrep ", "free ", "uptime ", "stat ", "wc ",
    "ollama ps", "ollama list"
)

def log(msg: str) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path: str, data: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

def run_cmd(cmd: List[str], timeout: int = 45) -> str:
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=timeout)
        return out
    except Exception as e:
        return f"CMD_FAIL: {e}"

def latest_screen_file() -> Optional[str]:
    # Find newest screen_*.png in cwd
    try:
        files = [f for f in os.listdir(".") if f.startswith(VISION_GLOB_PREFIX) and f.endswith(".png")]
        if not files and os.path.exists(VISION_LATEST_FALLBACK):
            return VISION_LATEST_FALLBACK
        if not files:
            return None
        files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        return files[0]
    except Exception:
        return None

def ocr_png(png_path: str) -> str:
    # Uses tesseract if installed; otherwise returns a message.
    if not os.path.exists(png_path):
        return "NO_PNG"
    if not ENABLE_VISION_OCR:
        return f"OCR_DISABLED (latest_png={png_path})"
    try:
        # write to temp base "ocr_tmp" -> creates ocr_tmp.txt
        subprocess.check_output(["tesseract", png_path, "ocr_tmp", "-l", "eng", "--psm", "6"],
                                text=True, stderr=subprocess.STDOUT, timeout=60)
        txt_path = "ocr_tmp.txt"
        if os.path.exists(txt_path):
            with open(txt_path, "r") as f:
                return f.read().strip()[:4000]
        return "OCR_OK_BUT_NO_TXT"
    except Exception as e:
        return f"OCR_FAIL: {e}"

def build_prompt(level: int, obs: Dict[str, Any]) -> str:
    # Strict JSON output request
    return f"""
You are Echo (local AI agent). Focus ONLY: AI/agent/vision/memory/spy.
NO finance, NO golem, NO ports, NO installs.

Task:
1) Summarize system state.
2) Identify one anomaly or improvement.
3) Suggest up to 2 SAFE read-only commands to run next.
4) Optional: propose ONE small code change snippet (python) for self-evolution.

Return JSON ONLY (no markdown, no extra text):
{{
  "state_summary": "...",
  "anomaly": "...",
  "next_act": ["cmd1", "cmd2"],
  "self_evo": "python snippet or empty"
}}

LEVEL={level}
OBS={json.dumps(obs)[:3500]}
""".strip()

def ask_ollama(prompt: str) -> str:
    try:
        return subprocess.check_output(["ollama", "run", MODEL, prompt], text=True, timeout=120)
    except Exception as e:
        return f"OLLAMA_FAIL: {e}"

def extract_json(text: str) -> Dict[str, Any]:
    # Robustly extract first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    blob = text[start:end+1]
    try:
        return json.loads(blob)
    except Exception:
        return {}

def is_safe_cmd(cmd: str) -> bool:
    c = cmd.strip()
    if not c:
        return False
    # allow exact "ollama ps" etc
    if any(c.startswith(p) for p in SAFE_PREFIXES):
        return True
    # allow safe file reads by extension
    if any(x in c for x in [".log", ".json", ".py", "echo_activity.log", "echo_agi_state.json", "echo_memory_ai.json"]):
        if c.startswith(("cat ", "tail ", "ls ", "grep ", "wc ", "head ")):
            return True
    return False

def safe_act(cmds: List[str]) -> List[Dict[str, str]]:
    results = []
    for cmd in (cmds or [])[:2]:
        cmd = cmd.strip()
        if not is_safe_cmd(cmd):
            results.append({"cmd": cmd, "status": "blocked"})
            continue
        out = run_cmd(["bash", "-lc", cmd], timeout=30)
        results.append({"cmd": cmd, "status": "ok", "out_head": out[:300]})
    return results

def main():
    os.makedirs("memory", exist_ok=True)
    open(LOG_FILE, "a").close()

    state = load_json(STATE_FILE, {"level": 1, "cycles": 0})
    level = int(state.get("level", 1))

    log(f"Echo AGI Clean START (model={MODEL}, level={level})")

    while True:
        state["cycles"] = int(state.get("cycles", 0)) + 1

        scan_text = run_cmd(SCAN_CMD, timeout=45)

        png = latest_screen_file()
        vision = ocr_png(png) if png else "NO_SCREENS_FOUND"

        obs = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "scan": scan_text[:6000],
            "vision": vision[:4000],
            "level": level,
            "cycles": state["cycles"]
        }

        prompt = build_prompt(level, obs)
        raw = ask_ollama(prompt)
        parsed = extract_json(raw)

        if not parsed:
            log("GAI: JSON_PARSE_FAIL (keeping loop alive)")
            parsed = {"state_summary": "parse_fail", "anomaly": "model_output_not_json", "next_act": [], "self_evo": ""}

        acts = safe_act(parsed.get("next_act", []))

        record = {
            "obs": obs,
            "gai_raw_head": raw[:800],
            "gai": parsed,
            "acts": acts
        }

        save_json(MEM_FILE, record)

        # Minimal ramp: increase to max 5
        if state["cycles"] % 3 == 0:
            level = min(level + 1, 5)
        state["level"] = level
        save_json(STATE_FILE, state)

        log(f"Cycle {state['cycles']} done | lvl={level} | anomaly={parsed.get('anomaly','')[:80]}")
        time.sleep(180)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Echo AGI Clean STOP (KeyboardInterrupt)")
