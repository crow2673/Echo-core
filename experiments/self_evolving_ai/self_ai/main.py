from __future__ import annotations

from pathlib import Path

from .memory import Memory
from .model import OllamaModel
from .tools import ToolBox


SYSTEM = """You are a persistent local artificial intelligence.

You are not only a language model. Your identity includes your model,
memory, tools, workspace, goals, observations, experiments, and the rules
that govern how you change yourself.

When you need a capability you do not have, describe the missing capability
and propose a tool or architectural change. Do not pretend you performed an
action you did not perform.

Prefer small, testable changes over uncontrolled self-modification.
"""


def main() -> None:
    root = Path.home() / ".self-evolving-ai"
    memory = Memory(root)
    tools = ToolBox(root / "workspace")
    model = OllamaModel()

    print("Self-Evolving AI v0.1")
    print("Type 'exit' to stop.")

    while True:
        try:
            user = input("\nYou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user.lower() == "exit":
            break
        if not user:
            continue

        context = memory.recent()
        prompt = (
            SYSTEM
            + "\nRecent memory:\n"
            + "\n".join(f"- {m['kind']}: {m['content']}" for m in context)
            + "\n\nUser request:\n"
            + user
        )

        answer = model.generate(prompt)
        print(f"AI > {answer}")
        memory.remember("conversation", f"User: {user}\nAI: {answer}")


if __name__ == "__main__":
    main()
