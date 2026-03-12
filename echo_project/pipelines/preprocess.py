import pandas as pd
import json
from pathlib import Path
import hashlib
import numpy as np

SEED = 42
np.random.seed(SEED)

# Correct path relative to project root
PROJECT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
RAW_PATH = DATA_DIR / "raw/data.csv"
PROC_PATH = DATA_DIR / "processed/data_processed.csv"
CONTRACT_PATH = DATA_DIR / "contracts/data_contract.json"

def compute_hash(file_path):
    return hashlib.sha256(file_path.read_bytes()).hexdigest()

def load_data():
    return pd.read_csv(RAW_PATH)

def preprocess(df):
    df = df.sort_values("id")  # deterministic order
    df["feature_norm"] = (df["feature"] - df["feature"].mean()) / df["feature"].std()
    return df

def save_contract(df):
    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    contract = {
        "columns": df.columns.tolist(),
        "dtypes": df.dtypes.apply(lambda x: str(x)).to_dict(),
        "hash": compute_hash(PROC_PATH)
    }
    with open(CONTRACT_PATH, "w") as f:
        json.dump(contract, f, indent=2)

def main():
    df = load_data()
    df = preprocess(df)

    PROC_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROC_PATH, index=False)

    save_contract(df)
    print(f"Processed data saved and contract generated at {CONTRACT_PATH}")

if __name__ == "__main__":
    main()
