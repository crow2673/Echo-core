# Self-Evolution Cycle v0.2

Run:

```bash
source .venv/bin/activate
python -m self_ai.run_evolution
```

The cycle asks the local model to:

1. observe a missing capability,
2. form a falsifiable hypothesis,
3. design a small change,
4. generate a candidate tool,
5. syntax-check the candidate,
6. evaluate whether it deserves promotion,
7. record the cycle in persistent memory.

**Promotion is deliberately not automatic yet.**

The experiment is testing whether an AI can generate *measurable candidate improvements*, not merely generate more code.
