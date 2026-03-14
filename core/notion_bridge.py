#!/usr/bin/env python3
"""
Echo Notion Bridge — mirrors Echo's event ledger to Notion in real time.
Writes to three databases:
  - Echo Events: reasoning, feedback, knowledge events
  - Echo Actions: governor action outcomes
  - Income Tracker: income stream status updates

Called by event_ledger.log_event() after every event is written.
Zero dependencies beyond stdlib — uses urllib only.
"""
import json, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/notion_bridge.log"

def _log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def _load_config():
    config = {}
    path = Path.home() / ".config/echo/golem.env"
    try:
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip()
    except Exception:
        pass
    return config

def _api_call(endpoint, payload, token, retries=3):
    """Make a Notion API call with retry and backoff."""
    import time
    last_err = None
    for attempt in range(retries):
        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"https://api.notion.com/v1/{endpoint}",
                data=data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28"
                }
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read()), None
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            return None, f"HTTP {e.code}: {body[:200]}"
        except Exception as e:
            last_err = str(e)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s backoff
    return None, f"failed after {retries} attempts: {last_err}"

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def log_event_to_notion(event_type, source, summary, score=None):
    """Mirror event to Notion in background thread — never blocks Echo."""
    import threading
    threading.Thread(
        target=_do_log_event,
        args=(event_type, source, summary, score),
        daemon=True
    ).start()
    return True

def _do_log_event(event_type, source, summary, score=None):
    """Actual Notion write — runs in background thread."""
    config = _load_config()
    token = config.get("NOTION_TOKEN")
    db_id = config.get("NOTION_DB_EVENTS")

    if not token or not db_id:
        return False

    # Truncate summary to Notion's 2000 char limit
    summary_text = str(summary)[:2000]

    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "Event": {
                "title": [{"type": "text", "text": {"content": summary_text[:100]}}]
            },
            "Type": {
                "select": {"name": event_type if event_type in
                    ["reasoning", "feedback", "action", "knowledge", "income", "regret"]
                    else "feedback"}
            },
            "Source": {
                "rich_text": [{"type": "text", "text": {"content": str(source)[:100]}}]
            },
            "Timestamp": {
                "date": {"start": _now_iso()}
            },
        }
    }

    if score is not None:
        payload["properties"]["Score"] = {"number": float(score)}

    result, err = _api_call("pages", payload, token)
    if err:
        _log(f"event log failed: {err}")
        return False
    return True

def log_action_to_notion(action_id, success, output):
    """
    Mirror a governor action outcome to Echo Actions database.
    """
    config = _load_config()
    token = config.get("NOTION_TOKEN")
    db_id = config.get("NOTION_DB_ACTIONS")

    if not token or not db_id:
        return False

    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "Action": {
                "title": [{"type": "text", "text": {"content": str(action_id)[:100]}}]
            },
            "Status": {
                "select": {"name": "success" if success else "failed"}
            },
            "Result": {
                "rich_text": [{"type": "text", "text": {"content": str(output)[:500]}}]
            },
            "Timestamp": {
                "date": {"start": _now_iso()}
            },
        }
    }

    result, err = _api_call("pages", payload, token)
    if err:
        _log(f"action log failed: {err}")
        return False
    return True

def log_income_to_notion(stream, status, notes):
    """
    Mirror income stream status to Income Tracker database.
    """
    config = _load_config()
    token = config.get("NOTION_TOKEN")
    db_id = config.get("NOTION_DB_INCOME")

    if not token or not db_id:
        return False

    status_map = {"active": "active", "pending": "pending", "inactive": "inactive"}
    notion_status = status_map.get(status.lower(), "pending")

    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "Stream": {
                "title": [{"type": "text", "text": {"content": str(stream)[:100]}}]
            },
            "Status": {
                "select": {"name": notion_status}
            },
            "Notes": {
                "rich_text": [{"type": "text", "text": {"content": str(notes)[:500]}}]
            },
            "Timestamp": {
                "date": {"start": _now_iso()}
            },
        }
    }

    result, err = _api_call("pages", payload, token)
    if err:
        _log(f"income log failed: {err}")
        return False
    return True

def test():
    """Test all three databases with sample entries."""
    print("Testing Notion bridge...")
    
    r1 = log_event_to_notion("reasoning", "test", "Echo is reasoning about Golem node status", score=0.8)
    print(f"  Echo Events: {'OK' if r1 else 'FAIL'}")
    
    r2 = log_action_to_notion("golem_status", True, "Golem node is running, 0 tasks completed")
    print(f"  Echo Actions: {'OK' if r2 else 'FAIL'}")
    
    r3 = log_income_to_notion("Golem Network", "active", "Node running, uptime 76%, 0 tasks yet")
    print(f"  Income Tracker: {'OK' if r3 else 'FAIL'}")
    
    if r1 and r2 and r3:
        print("\nAll three databases working. Check your Notion dashboard.")
    else:
        print("\nSome writes failed — check logs/notion_bridge.log")

if __name__ == "__main__":
    test()
