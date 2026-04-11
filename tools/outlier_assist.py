import sys
import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"

def assist(task_text):
    prompt = f"""You are helping complete an AI training task for Outlier AI.

The task is:
{task_text}

Provide a high quality, detailed, honest response. Be thorough. Write as a human expert would.
Do not mention that you are an AI. Just answer the task directly."""

    response = requests.post(OLLAMA_URL, json={
        "model": "qwen2.5:32b",
        "prompt": prompt,
        "stream": False
    }, timeout=300)

    result = response.json()
    print("\n=== ECHO DRAFT ===\n")
    print(result['response'])
    print("\n=== END DRAFT ===\n")
    print("Review the above, edit as needed, then paste into Outlier.")

if __name__ == "__main__":
    print("Paste your Outlier task below. Press Ctrl+D when done:\n")
    task = sys.stdin.read()
    assist(task)
