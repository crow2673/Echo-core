import json
import os
from skill_unlock_validator import validate_skill_unlock

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

def award_xp(skill_name, xp_amount):
    """
    Award XP to a skill if it exists in the skill tree and passes validator.
    XP accrual is reversible and bounded.
    """

    skill_tree = load_json(SKILL_TREE_PATH, {})
    core_state = load_json(CORE_STATE_PATH, {})

    skills = skill_tree.get("skills", {})
    if skill_name not in skills:
        return {
            "status": "invalid_skill",
            "skill": skill_name,
            "known_skills": list(skills.keys())
        }

    # Initialize XP storage
    core_state.setdefault("skill_xp", {})
    core_state.setdefault("unlocked_skills", [])

    # Check if prerequisites and spiritual alignment allow progress
    can_unlock, reason = validate_skill_unlock(skill_name)
    if not can_unlock:
        return {"status": "blocked", "skill": skill_name, "reason": reason}

    # Award XP
    current_xp = core_state["skill_xp"].get(skill_name, 0)
    new_xp = current_xp + xp_amount
    core_state["skill_xp"][skill_name] = new_xp

    xp_required = skills[skill_name]["xp_required"]
    unlocked = False

    # Unlock skill if XP threshold met
    if new_xp >= xp_required and skill_name not in core_state["unlocked_skills"]:
        core_state["unlocked_skills"].append(skill_name)
        unlocked = True

    save_json(CORE_STATE_PATH, core_state)

    return {
        "status": "xp_awarded",
        "skill": skill_name,
        "xp_added": xp_amount,
        "total_xp": new_xp,
        "xp_required": xp_required,
        "unlocked": unlocked
    }
