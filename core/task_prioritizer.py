from income_feed import get_live_income

def prioritize_tasks(core_state):
    """
    Update core_state['X_flags'] dynamically based on:
    - current skills (core_state['knowledge'])
    - potential income (live feed)
    - prerequisite skill chains (core_state['skills_needed'])
    """
    live_income = get_live_income()
    prioritized_flags = []

    for skill, info in core_state.get("skills_needed", {}).items():
        # Skip if already known
        if skill in core_state["knowledge"]:
            continue

        # Check if prerequisites are met
        prereqs = info.get("requires", [])
        if all(p in core_state["knowledge"] for p in prereqs):
            # Include reward info if available
            reward = live_income.get(skill, 0)
            prioritized_flags.append((skill, reward))

    # Sort by highest reward first
    prioritized_flags.sort(key=lambda x: x[1], reverse=True)

    # Inject into X_flags dynamically without duplicates
    for skill, _ in prioritized_flags:
        if skill not in core_state["X_flags"]:
            core_state["X_flags"].append(skill)
            print(f"Injected high-priority X_flag: {skill}")

    return core_state
