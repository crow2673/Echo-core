# Whole Organism Runtime v0.4

The AI is represented by `SelfEvolvingAI`, not by the language model alone.

The runtime owns:
- reasoning substrate
- persistent identity
- memory
- tools
- workspace
- candidate generation
- safety inspection
- evaluation
- evidence
- promotion and rollback

This is deliberately a composition boundary: future self-improvement can replace or upgrade any layer while the organism remains the persistent unit.

The goal is not to pretend the system is already generally intelligent. The goal is to make the architecture capable of testing increasingly broad forms of self-improvement without confusing generated text with demonstrated ability.