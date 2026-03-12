import json
from pathlib import Path
import hashlib
import pandas as pd

# Make paths project-root-relative
PROJECT_DIR = Path(__file__).parent.parent.resolve()
PROCESSED_PATH = PROJECT_DIR / "data/processed/data_processed.csv"
CONTRACT_PATH = PROJECT_DIR / "data/contracts/data_contract.json"

def validate_data_contract(processed_path, contract_path):
    df = pd.read_csv(processed_path)
    with open(contract_path) as f:
        contract = json.load(f)

    # Check columns
    assert list(df.columns) == contract["columns"], "Column mismatch"

    # Check dtypes
    dtypes = df.dtypes.apply(lambda x: str(x)).to_dict()
    assert dtypes == contract["dtypes"], "Dtype mismatch"

    # Check hash
    file_hash = hashlib.sha256(Path(processed_path).read_bytes()).hexdigest()
    assert file_hash == contract["hash"], "File hash mismatch"

    print("Data contract validated successfully!")

if __name__ == "__main__":
    validate_data_contract(PROCESSED_PATH, CONTRACT_PATH)
