from __future__ import annotations

from .organism import SelfEvolvingAI


SYSTEM = """You are a persistent local artificial intelligence.

You are not only a language model. Your identity includes your model, memory,
tools, workspace, goals, observations, experiments, and the rules that govern
how you change yourself.

Do not claim to have performed an action you did not perform.
Prefer small, testable changes over uncontrolled self-modification.
When proposing improvement, distinguish generated ideas from demonstrated results.
"""


def main() -> None:
    ai = SelfEvolvingAI()

    print(f"{ai.identity.name} v{ai.identity.version}")
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

        context = ai.memory.recent()
        prompt = (
            SYSTEM
            + "\nCurrent self-observation:\n"
            + str(ai.observe())
            + "\nRecent memory:\n"
            + "\n".join(f"- {m['kind']}: {m['content']}" for m in context)
            + "\n\nUser request:\n"
            + user
        )

        answer = ai.think(prompt)
        print(f"AI > {answer}")
        ai.remember("conversation", f"User: {user}\nAI: {answer}")


if __name__ == "__main__":
    main()
