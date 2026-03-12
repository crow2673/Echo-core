import pandas as pd
import joblib
from pathlib import Path
import json
import hashlib
from sklearn.linear_model import LinearRegression
import numpy as np

SEED = 42
np.random.seed(SEED)

PROJECT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
PROCESSED_PATH = DATA_DIR / "processed/data_processed.csv"

MODEL_DIR = PROJECT_DIR / "models"
MODEL_WEIGHTS_PATH = MODEL_DIR / "weights/model.pkl"
MODEL_CONTRACT_PATH = MODEL_DIR / "manifests/model_contract.json"

def compute_hash(file_path):
    return hashlib.sha256(file_path.read_bytes()).hexdigest()

def load_data():
    df = pd.read_csv(PROCESSED_PATH)
    X = df[["feature_norm"]].values
    y = df["feature"].values
    return X, y

def train_model(X, y):
    model = LinearRegression()
    model.fit(X, y)
    return model

def save_model(model):
    MODEL_WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_WEIGHTS_PATH)

def save_contract(model):
    MODEL_CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    contract = {
        "model_type": "LinearRegression",
        "input_features": ["feature_norm"],
        "output": "feature",
        "hash": compute_hash(MODEL_WEIGHTS_PATH)
    }
    with open(MODEL_CONTRACT_PATH, "w") as f:
        json.dump(contract, f, indent=2)

def main():
    X, y = load_data()
    model = train_model(X, y)
    save_model(model)
    save_contract(model)
    print(f"Model trained and saved at {MODEL_WEIGHTS_PATH}")
    print(f"Model contract saved at {MODEL_CONTRACT_PATH}")

if __name__ == "__main__":
    main()
