from task_manager_v2 import TaskManager
from datetime import date
tm = TaskManager()
tm.add_task("echo", date(2024,10,15), "Phase 2: Reflection tools", "high")
tm.add_task("echo", date(2024,10,20), "Integrate chat_memory.json", "high")
tm.add_task("echo", date(2024,10,25), "Companionship voice tuning")
tm.list_tasks()
