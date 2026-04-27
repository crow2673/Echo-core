#!/usr/bin/env python3
"""Notion task reader — pulls build tasks from a Notion database into Echo's queue."""
import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

LOG = Path.home() / "Echo/logs/notion_task_reader.log"
BUILD_QUEUE = Path.home() / "Echo/memory/build_queue.json"


def _log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def _get_config():
    env_file = Path.home() / ".config/echo/golem.env"
    token, db_id = "", ""
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("NOTION_TOKEN="):
                token = line.split("=", 1)[1].strip()
            if line.startswith("NOTION_DB_LEADS="):
                db_id = line.split("=", 1)[1].strip()
    return token or os.environ.get("NOTION_TOKEN", ""), db_id or os.environ.get("NOTION_DB_LEADS", "")


def run():
    token, db_id = _get_config()
    if not token or not db_id:
        _log("fetch failed: NOTION_TOKEN or NOTION_DB_LEADS not configured")
        return

    try:
        req = urllib.request.Request(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            data=json.dumps({}).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        tasks = []
        for page in data.get("results", []):
            props = page.get("properties", {})
            title = ""
            for v in props.get("Name", {}).get("title", []):
                title += v.get("text", {}).get("content", "")
            status = props.get("Status", {}).get("select", {}).get("name", "")
            if status.lower() in ("pending", "queued", "new") and title:
                tasks.append({"title": title, "notion_id": page["id"], "status": status})

        if tasks:
            existing = []
            if BUILD_QUEUE.exists():
                existing = json.loads(BUILD_QUEUE.read_text())
            existing_ids = {t.get("notion_id") for t in existing}
            new_tasks = [t for t in tasks if t["notion_id"] not in existing_ids]
            existing.extend(new_tasks)
            BUILD_QUEUE.write_text(json.dumps(existing, indent=2))
            _log(f"fetched {len(tasks)} tasks, {len(new_tasks)} new")
        else:
            _log("no pending tasks in Notion")

    except Exception as e:
        _log(f"fetch failed: {e}")


if __name__ == "__main__":
    run()
