# Add these lines to test_echo_chat.py AFTER imports, BEFORE chat loop:
from task_manager_v2 import TaskManager
tm = TaskManager()

def echo_memory_context():
    tasks = tm.parse_tasks()
    return f"Echo Memory Live: {len(tm.events)} events, {sum(sum(len(t) for t in d.values()) for d in tasks.values())} tasks. Next: {sorted(tasks['echo'].keys())[0] if 'echo' in tasks and tasks['echo'] else 'No echo tasks'}"

# Replace ALL old TaskManager code with: tm.parse_tasks(), tm.add_task()
# In chat response logic, add: context = echo_memory_context()
