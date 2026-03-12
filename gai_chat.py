#!/usr/bin/env python3
import subprocess, sys

print("🔥 GAI AMAIM Chat | Pilot, speak! I act.")

while True:
    pilot = input("Pilot> ").strip()
    if pilot.lower() in ['exit', 'off']:
        print("GAI: Offline.")
        break

    obs = subprocess.check_output(["./super_scan.sh"], text=True)[:2000]
    prompt = f"GAI anime. Pilot: '{pilot}'. PC: {obs}. Bold reply + act/plan."
    resp = subprocess.check_output(['ollama', 'run', 'gai', prompt], text=True).strip()
    print(f"🧠 GAI> {resp}")

    # Auto-acts
    if 'glm' in pilot.lower():
        subprocess.run(["python3", "echo_simple_agent.py", "ramp"])
