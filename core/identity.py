import json
import os
from pathlib import Path

IDENTITY_PATH = Path(__file__).parent / "echo_identity.json"

class IdentityViolation(Exception):
    pass

def load_identity():
    if not IDENTITY_PATH.exists():
        raise IdentityViolation("Identity file missing")

    with open(IDENTITY_PATH, "r") as f:
        identity = json.load(f)

    return identity

def assert_scope(path, identity):
    root = os.path.expanduser(identity["identity"]["root_path"])
    abs_path = os.path.abspath(path)

    if not abs_path.startswith(os.path.abspath(root)):
        raise IdentityViolation(f"Path outside identity scope: {abs_path}")

    return True
