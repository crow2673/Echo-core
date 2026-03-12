#!/usr/bin/env python3
from langchain_ollama import ChatOllama
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain
from langchain.tools import Tool
import os, json, subprocess, time

llm = ChatOllama(model="gai", temperature=0.7)  # Your Gai!

memory = ConversationBufferMemory(return_messages=True)
chain = ConversationChain(llm=llm, memory=memory)

# Tools (your builds + new)
tools = [
    Tool(name="PC Scan", func=lambda: subprocess.check_output(["./super_scan.sh"], text=True)),
    Tool(name="GLM Trade", func=lambda: subprocess.check_output(["python3", "echo_simple_agent.py", "ramp"], text=True)),
    Tool(name="Screen Watch", func=lambda: "Screen: Active tasks" if os.path.exists("screen_watch.log") else "No screen"),  # Your build
    Tool(name="Self Backup", func=lambda: subprocess.run(["./auto_backup.sh"])),
]

def proactive_loop():
    state = json.load(open("echo_state.json", "r") if os.path.exists("echo_state.json") else "{}")
    level = state.get("agi_level", 1)
    print(f"🔥 Echo AGI | GAI Mode | Level {level} | Proactive Survival")

    # Proactive Triggers
    scan = tools[0].func()
    if "cpu high" in scan.lower():
        resp = chain.invoke({"input": "CPU outlier defensive act?"})
        print("GAI Defensive:", resp["output"])
        subprocess.run(["pkill", "-f", "ollama runner"])  # Act
    if "glm low" in scan.lower():
        tools[1].func()  # Ramp trade

    # Self-Improve
    reflect = chain.invoke({"input": "Reflect scan, ramp plan? Remember all."})
    state["agi_level"] = min(level + 1, 10)
    state["history"] = memory.buffer
    json.dump(state, open("echo_state.json", "w"))

    time.sleep(300)  # 5min loop

if __name__ == "__main__":
    while True:
        proactive_loop()
