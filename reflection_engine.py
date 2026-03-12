from task_manager_v2 import TaskManager
tm = TaskManager()
parsed_tasks = tm.parse_tasks()
print("=== ECHO REFLECTION ===")
print(f"📊 Memory: {len(tm.events)} events | Active tasks: {sum(sum(len(t) for t in dates.values()) for dates in parsed_tasks.values())}")
print(f"🔥 High priority: {'echo' in parsed_tasks}")
print("\nNext actions:")
for wf, dates in parsed_tasks.items():
    upcoming = sorted(dates.keys())[0] if dates else None
    if upcoming:
        print(f"  {wf}: {upcoming} - {dates[upcoming][0]['desc']}")
print("\n💡 Insight: Trading steady (ramp/hold). 150 chat msgs integrated. Phase 2: Reflection live!")
