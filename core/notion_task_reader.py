#!/usr/bin/env python3
"""
Echo Notion Task Reader
Reads the Build Queue page in Notion every governor cycle.
Picks up tasks marked 'ready', attempts them, writes results back.
This is the communication layer between Claude, ChatGPT, and Echo.
"""
import json, urllib.request, subprocess, sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/notion_task_reader.log"
BUILD_QUEUE_PAGE_ID = "32419208c07d817e9093c17e4fe573af"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def load_config():
    config = {}
    try:
        for line in (Path.home() / ".config/echo/golem.env").read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip()
    except Exception:
        pass
    return config

def fetch_build_queue(token):
    """Fetch the Build Queue page content from Notion."""
    try:
        req = urllib.request.Request(
            f"https://api.notion.com/v1/blocks/{BUILD_QUEUE_PAGE_ID}/children",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("results", [])
    except Exception as e:
        log(f"fetch failed: {e}")
        return []

def parse_tasks(blocks):
    """Parse task blocks from page content."""
    tasks = []
    for block in blocks:
        if block.get("type") == "code":
            text = ""
            for rt in block.get("code", {}).get("rich_text", []):
                text += rt.get("plain_text", "")
            if "Status: ready" in text:
                task = {}
                for line in text.splitlines():
                    if ": " in line:
                        k, v = line.split(": ", 1)
                        task[k.strip()] = v.strip()
                if task.get("ID") and task.get("Task"):
                    task["block_id"] = block["id"]
                    tasks.append(task)
    return tasks

def execute_task(task):
    """Execute a task from the build queue."""
    task_text = task.get("Task", "")
    context = task.get("Context", "")
    log(f"executing task: {task.get('ID')} — {task_text[:60]}")

    # Route task to appropriate handler
    result = "unknown task type"

    # Standing task addition
    if "standing_tasks.json" in task_text or "standing task" in task_text.lower():
        try:
            sf = BASE / "memory/standing_tasks.json"
            data = json.loads(sf.read_text())
            # Extract the task description from the task text
            new_task_text = task_text.split('"')[1] if '"' in task_text else task_text
            new_id = f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            data["tasks"].append({
                "id": new_id,
                "task": new_task_text,
                "weight": 1.0,
                "min_weight": 0.3,
                "max_weight": 1.5,
                "wins": 0,
                "losses": 0
            })
            sf.write_text(json.dumps(data, indent=2))
            result = f"OK — added standing task '{new_task_text[:60]}' as {new_id}"
        except Exception as e:
            result = f"FAIL — {e}"

    # Shell command execution
    elif task_text.startswith("bash:") or task_text.startswith("run:"):
        cmd = task_text.split(":", 1)[1].strip()
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                             cwd=str(BASE), timeout=60)
            result = f"OK — {r.stdout.strip()[:200]}" if r.returncode == 0 else f"FAIL — {r.stderr.strip()[:200]}"
        except Exception as e:
            result = f"FAIL — {e}"

    # Python execution
    elif task_text.startswith("python:"):
        code = task_text.split(":", 1)[1].strip()
        try:
            exec(code, {"BASE": BASE})
            result = "OK — python executed"
        except Exception as e:
            result = f"FAIL — {e}"

    return result

def update_task_result(token, block_id, task, result):
    """Update the task block in Notion with the result."""
    try:
        task["Status"] = "done" if result.startswith("OK") else "failed"
        task["Result"] = result[:200]
        task["Completed"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        new_text = "\n".join(f"{k}: {v}" for k, v in task.items()
                            if k not in ["block_id"])

        payload = json.dumps({
            "code": {
                "rich_text": [{"type": "text", "text": {"content": new_text}}],
                "language": "plain text"
            }
        }).encode()

        req = urllib.request.Request(
            f"https://api.notion.com/v1/blocks/{block_id}",
            data=payload,
            method="PATCH",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            json.loads(r.read())
        log(f"task {task.get('ID')} updated in Notion")
    except Exception as e:
        log(f"update failed: {e}")

def run():
    config = load_config()
    token = config.get("NOTION_TOKEN")
    if not token:
        return

    blocks = fetch_build_queue(token)
    if not blocks:
        return

    tasks = parse_tasks(blocks)
    if not tasks:
        return

    log(f"found {len(tasks)} ready tasks")
    for task in tasks[:1]:  # process one task per cycle
        result = execute_task(task)
        update_task_result(token, task["block_id"], task, result)
        log(f"task {task.get('ID')}: {result[:80]}")

        try:
            from core.event_ledger import log_event
            log_event("action", "notion_task_reader",
                f"task {task.get('ID')}: {result[:100]}",
                score=1.0 if result.startswith("OK") else -1.0)
        except Exception:
            pass

if __name__ == "__main__":
    run()
