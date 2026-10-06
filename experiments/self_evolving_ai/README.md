# Self-Evolving AI — v0.1

This is an experimental branch for a downloadable AI whose identity is the **whole runtime**, not just the language model.

## Concept

The AI consists of:

- a local language model
- persistent identity and goals
- memory
- tool use
- an execution environment
- self-observation
- experiments
- controlled self-modification

The model is the cognitive substrate. The runtime is the rest of the artificial organism.

## First principle

The AI may propose changes to itself, but v0.1 never replaces the running installation blindly.

A change follows:

1. Observe a limitation.
2. Propose a change.
3. Create an isolated candidate.
4. Test the candidate.
5. Compare results against the current version.
6. Keep the candidate only when the evaluation passes.
7. Record what changed and why.

## Model distribution

The Git repository contains the AI runtime, not multi-gigabyte model weights.

The installer provisions a local model through Ollama. This makes the finished installation self-contained on the user's machine while keeping source control practical.

Default model: `qwen2.5:7b`.

## Run

```bash
./install.sh
./run.sh
```

The goal of this project is not to claim human-level intelligence. The goal is to experimentally determine whether a persistent AI can safely acquire and improve its own capabilities.
