from pathlib import Path

from .evolution_cycle import EvolutionSpec
from .organism import SelfEvolvingAI


def main() -> None:
    print("Self-evolution requires a concrete benchmark spec.")
    print("Use SelfEvolvingAI.evolve(EvolutionSpec(...)) so the baseline and")
    print("success criteria exist before a candidate is generated.")


if __name__ == "__main__":
    main()
