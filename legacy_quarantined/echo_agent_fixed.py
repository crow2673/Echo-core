#!/usr/bin/env python3
# Echo Agent: ReAct + Ollama + Golem/Trading + Workflow (Your Grok Builds)

import json
import subprocess
import ollama
from langchain.agents import create_react_agent, AgentExecutor
from langchain.tools import Tool
from langchain_ollama import OllamaLLM

# Tools: Golem Trade + Workflow (Your Files)
def golem_trade(action):
    subprocess.run(["python3", "trading_bot.py", action], capture_output=True)
    return "Trade exec: GLM ramped via bot."

def outlier_workflow(task):
    subprocess.run(["python3", "workflow_intake_auto.py", task], capture_output=True)
    return "Outlier task intake: Autonomy loop."

tools = [
    Tool(name="GolemTrade", func=golem_trade, description="Trade GLM/offers e.g. 'buy' 'accept VM'"),
    Tool(name="OutlierIntake", func=outlier_workflow, description="Process Outlier tasks to Echo")
]

# Agent Setup
llm = OllamaLLM(model="qwen2.5:7b")
prompt = "Reason step-by-step. Use tools for trades/GLM/Outlier. Goal: Earnings + Autonomy."
agent = create_react_agent(llm, tools, prompt)
agent_exec = AgentExecutor(agent=agent, tools=tools, verbose=True)

# Run/Test
if __name__ == "__main__":
    query = input("Query: ") or "Ramp Golem trades + Outlier sync"
    result = agent_exec.invoke({"input": query})
    print("Echo:", result['output'])
    # Save memory
    with open('echo_memory.json', 'a') as f:
        json.dump({"query": query, "result": result['output'], "ts": time.time()}, f)
        f.write('\n')
