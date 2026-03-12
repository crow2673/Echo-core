#!/usr/bin/env python3
import time
import json
import sys

def main(mode='ramp'):
    print(f"Trading bot running in '{mode}' mode...")

    # Simulated trading loop
    for i in range(5):
        print(f"Simulated trade {i+1} in {mode} mode")
        time.sleep(1)

    # Optionally: Query AI for trade strategy
    try:
        import ollama
        with open('echo_memory.json', 'r') as f:
            recent_memory = f.readlines()[-10:]

        ai_resp = ollama.chat(model='qwen2.5:7b', messages=[
            {'role': 'system', 'content': 'You are Echo Jarvis. Suggest trading strategy adjustments.'},
            {'role': 'user', 'content': f"Trading memory: {recent_memory}. Any adjustments to the strategy?"}
        ])
        print("AI Trading Suggestion:", ai_resp['message']['content'][:200])
    except Exception as e:
        print(f"⚠️ AI trading suggestion error: {e}")

    print("Trading bot completed.")

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'ramp'
    main(mode)
