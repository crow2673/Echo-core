import json
from pathlib import Path
import hashlib
import sys

CAPSULE_PATH = Path("core/continuity_capsule.json")

def compute_hash(file_path):
    return hashlib.sha256(file_path.read_bytes()).hexdigest()

def load_capsule():
    with open(CAPSULE_PATH) as f:
        return json.load(f)

def verify_identity(capsule):
    identity_file = Path(capsule["identity"]["identity_file"]).expanduser()
    if not identity_file.exists():
        print(f"ERROR: Identity file missing: {identity_file}")
        return False
    print(f"Identity verified: {identity_file}")
    return True

def verify_models(capsule):
    models_info = capsule["models"]
    base_path = Path(models_info["location"]).expanduser()
    for fname, expected_hash in models_info["files"].items():
        fpath = base_path / fname
        if not fpath.exists():
            print(f"ERROR: Model missing: {fpath}")
            return False
        actual_hash = compute_hash(fpath)
        if actual_hash != expected_hash:
            print(f"ERROR: Model hash mismatch: {fpath}")
            return False
    print(f"All models verified in {base_path}")
    return True

def verify_contracts(capsule):
    contracts_info = capsule["contracts"]
    base_path = Path(contracts_info["location"]).expanduser()
    contract_files = list(base_path.rglob(contracts_info["pattern"]))
    if len(contract_files) != contracts_info["expected_count"]:
        print(f"ERROR: Contract count mismatch in {base_path} ({len(contract_files)} found, expected {contracts_info['expected_count']})")
        return False
    print(f"All contracts verified in {base_path}")
    return True

def verify_pipelines(capsule):
    pipelines_info = capsule["pipelines"]
    base_path = Path(pipelines_info["location"]).expanduser()
    pipeline_files = list(base_path.glob("*.py"))
    if len(pipeline_files) != pipelines_info["expected_count"]:
        print(f"ERROR: Pipeline count mismatch in {base_path} ({len(pipeline_files)} found, expected {pipelines_info['expected_count']})")
        return False
    print(f"All pipelines verified in {base_path}")
    return True

def main():
    capsule = load_capsule()
    print(f"Boot verifying Echo - Authority: {capsule['authority']}")
    
    if capsule["boot_rules"]["load_identity_first"]:
        if not verify_identity(capsule):
            sys.exit("ABORT: Identity verification failed")
    
    if capsule["boot_rules"]["verify_models"]:
        if not verify_models(capsule):
            sys.exit("ABORT: Model verification failed")
    
    if capsule["boot_rules"]["verify_contracts"]:
        if not verify_contracts(capsule):
            sys.exit("ABORT: Contract verification failed")
    
    if not verify_pipelines(capsule):
        sys.exit("ABORT: Pipeline verification failed")
    
    print("Echo boot verification complete. All systems nominal.")

if __name__ == "__main__":
    main()
