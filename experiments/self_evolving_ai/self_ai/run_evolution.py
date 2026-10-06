from pathlib import Path

from .evolution_cycle import SelfEvolutionCycle
from .model import OllamaModel


def main() -> None:
    root = Path.home() / ".self-evolving-ai"
    cycle = SelfEvolutionCycle(root, OllamaModel())
    result = cycle.run()

    print("\n=== SELF-EVOLUTION CYCLE ===")
    print("OBSERVATION:", result.observation)
    print("HYPOTHESIS:", result.hypothesis)
    print("ACTION:", result.action)
    print("TEST:", result.test_result)
    print("DECISION:", result.decision)


if __name__ == "__main__":
    main()
