import json
import os

BASE_DIR = os.path.dirname(__file__)
SKILL_TREE_PATH = os.path.join(BASE_DIR, "../memory/skill_tree.schema.json")
CORE_STATE_PATH = os.path.join(BASE_DIR, "../memory/core_state.json")

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def validate_skill_unlock(skill_name):
    """
    Checks if a skill can be unlocked according to:
    1. Prerequisites
    2. Spiritual alignment
    3. Reversibility (XP can go down)
    Returns True/False and reason.
    """
    skill_tree = load_json(SKILL_TREE_PATH, {})
    core_state = load_json(CORE_STATE_PATH, {})

    skills = skill_tree.get("skills", {})
    if skill_name not in skills:
        return False, "Skill not in skill tree"

    # Check prerequisites
    prereqs = skills[skill_name].get("prerequisites", [])
    unlocked_skills = core_state.get("unlocked_skills", [])
    missing = [p for p in prereqs if p not in unlocked_skills]
    if missing:
        return False, f"Missing prerequisites: {missing}"

    # Spiritual alignment check (can extend rules here)
    alignment = skill_tree.get("alignment", {})
    if alignment.get("override_rule") == "Spiritual integrity overrides progress":
        misaligned = core_state.get("misaligned_skills", [])
        if skill_name in misaligned:
            return False, "Blocked by spiritual alignment"

    return True, "Unlock allowed"

def unlock_skill(skill_name):
    """Attempt to unlock skill if valid."""
    valid, reason = validate_skill_unlock(skill_name)
    core_state = load_json(CORE_STATE_PATH, {})

    if not valid:
        return {"status": "blocked", "skill": skill_name, "reason": reason}

    if skill_name not in core_state.get("unlocked_skills", []):
        core_state.setdefault("unlocked_skills", []).append(skill_name)
        save_json(CORE_STATE_PATH, core_state)
        return {"status": "unlocked", "skill": skill_name}

    return {"status": "already_unlocked", "skill": skill_name}
