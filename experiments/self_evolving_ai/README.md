# Self-Evolving AI — v0.6

This experiment is a downloadable local AI runtime whose identity is the
**whole organism**, not just the language model.

## What is the organism?

The runtime combines:

- local language model
- persistent identity and goals
- memory
- tools and workspace
- self-observation
- candidate generation
- static safety inspection
- deterministic measurement
- evidence ledger
- promotion and rollback
- evolution journal

The model is the reasoning substrate. The organism is the complete system around
that substrate.

## One canonical evolution path

The project now has one authority for self-modification:

observe limitation -> form hypothesis -> generate candidate -> static safety gate -> benchmark baseline and candidate -> require measurable improvement -> record evidence -> promote -> retain rollback

The language model can propose a change, but it cannot declare its own change successful.

## Why the benchmark comes first

An experiment must define its cases and expected results before a candidate is
generated. This prevents the system from changing the test after seeing the
result.

SelfEvolvingAI.evolve(EvolutionSpec(...)) is the public entry point.

## Candidate execution boundary

Candidates are executed in a separate Python process with a timeout and isolated
temporary working directory. This is **not a security sandbox**. Static AST
inspection is still mandatory, and hostile candidate code must not be treated as
safe. Stronger OS/container isolation is a future hardening step.

## Installation

The repository contains runtime code, not multi-gigabyte model weights.

The installer expects Ollama to already be installed and pulls the default
local model qwen2.5:7b.

    ./install.sh
    ./run.sh

## Important limitation

This version demonstrates a real, measured self-modification mechanism for
bounded capabilities. It does **not** prove general intelligence, autonomous
income, or unrestricted self-improvement.

The next major engineering target is expanding the benchmark/experiment
registry and strengthening candidate isolation without creating a second
evolution engine.
