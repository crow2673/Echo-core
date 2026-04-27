#!/usr/bin/env python3
"""Notion bridge — logs Echo actions and events to Notion databases."""
import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

LOG = Path.home() / "Echo/logs/notion_bridge.log"


def _get_token():
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("NOTION_TOKEN="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("NOTION_TOKEN", "")


def _get_db_id(key):
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return os.environ.get(key, "")


def _log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def _post(endpoint, payload, token):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.notion.com/v1/{endpoint}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def log_action_to_notion(action_id: str, success: bool, output: str):
    token = _get_token()
    db_id = _get_db_id("NOTION_ACTIONS_DB")
    if not token or not db_id:
        _log("action log skipped — NOTION_TOKEN or NOTION_ACTIONS_DB not configured")
        return
    try:
        _post("pages", {
            "parent": {"database_id": db_id},
            "properties": {
                "Name": {"title": [{"text": {"content": action_id}}]},
                "Success": {"checkbox": success},
                "Output": {"rich_text": [{"text": {"content": output[:500]}}]},
                "Timestamp": {"date": {"start": datetime.now().isoformat()}},
            }
        }, token)
        _log(f"action logged: {action_id} — {'ok' if success else 'fail'}")
    except Exception as e:
        _log(f"action log failed: {e}")


def log_income_to_notion(source: str, amount: float, notes: str = ""):
    token = _get_token()
    db_id = _get_db_id("NOTION_INCOME_DB")
    if not token or not db_id:
        _log("event log skipped — NOTION_TOKEN or NOTION_INCOME_DB not configured")
        return
    try:
        _post("pages", {
            "parent": {"database_id": db_id},
            "properties": {
                "Source": {"title": [{"text": {"content": source}}]},
                "Amount": {"number": amount},
                "Notes": {"rich_text": [{"text": {"content": notes[:300]}}]},
                "Date": {"date": {"start": datetime.now().isoformat()}},
            }
        }, token)
        _log(f"income logged: {source} ${amount}")
    except Exception as e:
        _log(f"event log failed: {e}")
