from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
import subprocess

llm = ChatOllama(model="qwen2.5:7b", temperature=0)

def golem_tool(query):
    """Golem earnings/status."""
    return subprocess.getoutput("yagna payment status --network polygon --precise")

agent = create_react_agent(llm, [golem_tool])
result = agent.invoke({"messages": [HumanMessage(content="Echo: Golem report + optimize.")]})
print(result['messages'][-1].content)
