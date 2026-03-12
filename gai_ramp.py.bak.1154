#!/usr/bin/env python3
import os, json, time, subprocess

STATE_FILE = 'gai_omni.json'
MODEL = 'gai'

def load_state(key, default=None):
    try:
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
        return data.get(key, default)
    except:
        return default

def save_state(key, value):
    data = load_state(key, {})
    data[key] = value
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def super_observe():
    subprocess.run(['./super_scan.sh'], stdout=open('gai_omni.txt', 'w'))

def ramp_loop():
    level = load_state('autonomy_level', 1)
    print(f"🚀 GAI OMNI Level {level}/10 | Full PC Awareness")

    super_observe()  # All data

    with open('gai_omni.txt', 'r') as f:
        obs = f.read()[:4000]  # Full context

    prompt = f"""GAI AMAIM mode. Level {level}. Comprehend FULL PC state, outliers, threats/opps. Plan ramp action/user aid. Anime bold.

State: {obs}

Ramp/Act/Improve:"""
    try:
        resp = subprocess.check_output(['ollama', 'run', MODEL, prompt], text=True, timeout=120).strip()
    except:
        resp = "Ollama down – manual ramp."

    print("🧠 GAI OMNI:", resp[:300])

    # Smart Act
    if any(word in resp.lower() for word in ['outlier', 'high cpu', 'task', 'earn', 'glm']):
        level += 1
        save_state('autonomy_level', min(level, 10))
        print("🔥 RAMP ++ | Action...")
        subprocess.run(['yagna', 'payment', 'status', '--precise'])
        if 'ollama' in resp.lower():
            subprocess.run(['ollama', 'ps'])  # Manage

    save_state('last_resp', resp)
    time.sleep(60)

if __name__ == '__main__':
    while True:
        ramp_loop()
