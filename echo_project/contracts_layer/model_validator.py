import json
from pathlib import Path
import hashlib
import joblib

PROJECT_DIR = Path(__file__).parent.parent.resolve()
MODEL_WEIGHTS_PATH = PROJECT_DIR / "models/weights/model.pkl"
MODEL_CONTRACT_PATH = PROJECT_DIR / "models/manifests/model_contract.json"

def validate_model_contract(model_path, contract_path):
    model = joblib.load(model_path)
    with open(contract_path) as f:
        contract = json.load(f)

    # Check hash
    file_hash = hashlib.sha256(Path(model_path).read_bytes()).hexdigest()
    assert file_hash == contract["hash"], "Model file hash mismatch"

    # Basic type check
    assert contract["model_type"] == type(model).__name__, "Model type mismatch"
    print("Model contract validated successfully!")

if __name__ == "__main__":
    validate_model_contract(MODEL_WEIGHTS_PATH, MODEL_CONTRACT_PATH)
