#!/usr/bin/env python3
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()

def run_step(script_path):
    print(f"Running {script_path}...")
    result = subprocess.run(["python", str(script_path)], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(f"{script_path} failed!")

def main():
    steps = [
        PROJECT_DIR / "pipelines/preprocess.py",
        PROJECT_DIR / "pipelines/train.py",
        PROJECT_DIR / "contracts_layer/validator.py",
        PROJECT_DIR / "contracts_layer/model_validator.py",
    ]
    for step in steps:
        run_step(step)
    print("All steps completed successfully!")

if __name__ == "__main__":
    main()
