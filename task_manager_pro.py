from pathlib import Path
from collections import defaultdict
from datetime import date, datetime
from typing import Dict, Any, List
import json
from dateutil.parser import parse

MEMORY_FILE = Path("echo_memory.json")

class TaskManagerPro:
    def __init__(self):
        self.workflows = defaultdict(lambda: defaultdict(list))  # wf → date → tasks
        self.trading_logs: List[Dict] = []  # All {"ts", "glml", "action", ...}

    def load_memory(self) -> Dict[str, Any]:
        if not MEMORY_FILE.exists():
            return {}
        content = MEMORY_FILE.read_text()
        try:
            # Try as single object first
            return json.loads(content)
        except json.JSONDecodeError:
            # FALLBACK: Split & parse multiple objects into array
            objects = []
            for line in content.splitlines():
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    try:
                        objects.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            print(f"Parsed {len(objects)} log entries from malformed JSON")
            return {"logs": objects}  # Wrapper

    def parse_all(self, memory: Dict[str, Any]):
        # Trading logs
        logs = []
        if "logs" in memory:
            logs.extend(memory["logs"])
        for key, val in memory.items():
            if isinstance(val, dict) and "ts" in val:
                logs.append(val)
        self.trading_logs = logs

        # Workflows (old logic)
        for wf_id, data in memory.items():
            if isinstance(data, dict) and "tasks" in data:
                for date_str, task_data in data["tasks"].items():
                    if isinstance(task_data, dict):
                        try:
                            due_date = parse(date_str).date()
                            self.workflows[wf_id][due_date].append(task_data)
                        except ValueError:
                            pass

    def stats(self):
        return {
            "trading_signals": len(self.trading_logs),
            "workflows": dict(self.workflows),
            "recent_trades": self.trading_logs[-5:] if self.trading_logs else []
        }

if __name__ == "__main__":
    tm = TaskManagerPro()
    memory = tm.load_memory()
    print("Raw Memory:", memory)
    tm.parse_all(memory)
    print("STATS:", tm.stats())
    print("Recent Trades:")
    for log in tm.trading_logs[-3:]:
        ts = datetime.fromtimestamp(log["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {ts}: glml={log['glml']:.4f}, action={log['action']}, hold={log['order']['hold']:.4f}")
