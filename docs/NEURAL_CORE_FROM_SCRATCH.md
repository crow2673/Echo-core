# Echo Neural Core — From-Scratch Research Design

**Status:** Proposed research direction; not implemented  
**Scope:** Experimental architecture only. This document does not authorize changes to the existing Echo runtime.

## 1. Design decision

Build Echo's own neural learning core around **reasoning support, prediction, and adaptation**, with language as a communication interface rather than making fluent text generation the first objective.

The first objective is not to recreate a large commercial language model. It is to establish a small, measurable learning system that can:

1. Observe a sequence of states or events.
2. Build an internal representation of the current situation.
3. Predict a future state or outcome.
4. Compare the prediction with what actually happened.
5. Measure the error and update its own parameters.
6. Demonstrate improvement on held-out tests.

A prediction loop is a foundation for useful learning, not proof of general reasoning or intelligence. Those capabilities must be tested independently.

## 2. Meaning of “from scratch”

The experimental neural model must begin with **randomly initialized weights**. It must not load Qwen, Llama, or another pretrained model's weights, adapters, hidden states, or embeddings as its own learned intelligence.

Permitted foundations:

- Python and PyTorch or another documented numerical framework.
- Standard hardware acceleration libraries.
- Published papers and established algorithms.
- Properly licensed training data, synthetic data, and data created for experiments.
- Existing models as optional external baselines or teachers, provided their outputs are clearly labeled and are not represented as Echo's own learned weights.

The first experiment should not depend on a teacher model. A teacher may be evaluated later as an optional comparison.

“From scratch” does not mean writing matrix multiplication, GPU drivers, or every low-level numerical primitive ourselves. The goal is ownership of the model architecture, initialization, training process, learned weights, evaluation, and checkpoints.

## 3. Proposed modular architecture

```
                    ECHO INTERACTION LAYER
               language input / language output
                              |
                              v
                    CONTEXT ENCODER
             events, observations, task state
                              |
                              v
                     NEURAL LEARNING CORE
                 learned internal representation
                              |
               +--------------+--------------+
               |              |              |
               v              v              v
          PREDICTOR        PLANNER       UNCERTAINTY
        future states    candidate paths  confidence
               |              |              |
               +--------------+--------------+
                              |
                              v
                     EVALUATION LOOP
             prediction vs. observed outcome
                              |
                              v
                     WEIGHT UPDATES
                 offline, measured training
                              |
                              v
                    VERSIONED CHECKPOINTS
```

Supporting system modules remain distinct from the neural model:

- **Memory store:** durable events, observations, and retrieved context.
- **Safety governor:** permissions, action boundaries, and stop conditions.
- **Tool/action adapters:** controlled access to external tools.
- **Experiment ledger:** datasets, configurations, metrics, checkpoints, and results.
- **Language interface:** translates between human instructions and structured internal inputs/outputs.

The neural model does not receive unrestricted authority to execute actions or rewrite its own production code.

## 4. Development stages

### Stage 0 — Reproducible experimental shell

Create an isolated experiment directory, independent of Echo's production services.

Deliverables:

- Reproducible Python environment and dependency lock.
- Explicit random seeds and configuration files.
- Dataset versioning and train/validation/test separation.
- Checkpoint save/load and experiment metadata.
- CPU-first test path; GPU acceleration optional.
- No credentials, private Echo memory database, or production secrets.

**Exit test:** A clean environment can reproduce the same small training run and report its metrics.

### Stage 1 — First neural learner: sequence prediction

Start with a small neural network with randomly initialized parameters. Train it on generated sequences with known rules, then on a small, properly licensed real dataset if useful.

The model receives a history and predicts the next value, event, or state.

Measure:

- Training loss and held-out validation loss.
- Prediction accuracy or task-appropriate error.
- Performance against simple baselines.
- Generalization to sequences not seen during training.
- Behavior when observations are noisy or incomplete.

**Exit test:** It beats a documented simple baseline on held-out examples, repeatedly, with reproducible results.

### Stage 2 — State representation and world model

Move from predicting isolated next values to predicting structured state transitions.

Represent an observation as a state, apply an action or event, and predict the next state. Begin in a small synthetic environment where the correct transition rules are known.

Measure transition accuracy, uncertainty calibration, and performance under changed conditions.

**Exit test:** The model predicts state changes better than baseline methods on unseen scenarios.

### Stage 3 — Planning and decision evaluation

Use the learned transition model to compare candidate action sequences. Initially operate only in simulation.

Evaluate decisions against a fixed objective and compare predicted outcomes with actual outcomes. Record failures as carefully as successes.

**Exit test:** Planning improves a predeclared objective over a baseline without violating safety constraints.

### Stage 4 — Language interface

Add language after the core has demonstrated useful learning behavior.

The language subsystem may initially be a separate replaceable component. If Echo's own language model is later trained from scratch, it must have its own tokenizer, architecture, randomly initialized weights, dataset provenance, and language benchmarks.

Do not confuse a structured reasoning interface with a fully capable language model.

**Exit test:** The interface can faithfully translate requests into structured tasks and explain results without changing the measured behavior of the underlying learner.

### Stage 5 — Controlled Echo integration

Connect the experimental core to Echo through a narrow adapter.

- Read-only observations first.
- No production memory writes by default.
- No autonomous financial, system, or external actions.
- Explicit human approval for any action with external effects.
- Shadow-mode comparisons against existing behavior.
- Rollback to the previous system at all times.

The existing Echo/Qwen setup remains available as a baseline and fallback until the new system passes defined acceptance tests. It is not silently replaced.

## 5. First $5 experiment

The initial cloud budget is **$5 maximum**. This is a research budget, not a promise that a capable model can be trained for $5.

Prioritize a small GPU or CPU experiment that proves the training pipeline works:

1. Create the isolated environment.
2. Generate a small synthetic sequence dataset.
3. Initialize a small model from random weights.
4. Train for a short, bounded run.
5. Evaluate on held-out sequences.
6. Save the model checkpoint and experiment report.
7. Stop the compute instance and verify it is stopped.

The test is successful if it produces a reproducible training run, a checkpoint, and honest evaluation results. A low loss on training data alone is not success.

Do not start a paid instance until the provider's prepaid-credit behavior, storage charges, shutdown behavior, and spending controls are understood. Do not rely on a manual timer as a guaranteed billing cap.

## 6. Hardware strategy

Initial development should be small enough to run on CPU for correctness tests. Use GPU acceleration only when it materially shortens an experiment.

The previously documented home system (RTX 3060 12 GB VRAM, 32 GB system RAM) can support small experiments, but it is not sufficient to train a competitive general-purpose foundation model from scratch.

The first goal is not parameter count. It is a reliable learning loop and a model whose behavior can be measured.

## 7. Required experiment record

Every training run should record:

- Model architecture and parameter count.
- Random initialization seed.
- Dataset identity, provenance, license, and split.
- Training configuration and code revision.
- Hardware, elapsed time, and estimated cost.
- Training and validation metrics.
- Baseline comparison.
- Known limitations and failure examples.
- Checkpoint hash and storage location.

No claim of learning, improvement, reasoning, or autonomy should be made without a corresponding test result.

## 8. Safety and governance

- Training and evaluation are separate from production execution.
- A model cannot approve its own promotion.
- Promotion requires predefined tests and human review.
- Checkpoints are versioned; rollback must be tested.
- No online weight updates during unsupervised production operation in the initial design.
- External actions remain governed by Echo's permission and safety layers.
- Private user data is excluded from training unless explicitly selected, reviewed, and appropriately protected.

## 9. First implementation milestone

Build **Stage 0 and Stage 1 only**.

The first concrete artifact should be a small, independently runnable sequence-prediction experiment with:

- randomly initialized weights,
- a generated dataset,
- a training script,
- an evaluation script,
- a saved checkpoint,
- and a concise report showing baseline versus trained performance.

Do not build the entire architecture before this milestone works.

## 10. Open design decisions

These should be decided by experiment rather than assumed:

- Whether the first model should be a small MLP, recurrent network, or compact transformer.
- Which state representation best fits Echo's observations and tasks.
- Whether one shared model or several specialized models work better.
- Which memory retrieval method provides measurable benefit.
- When language generation should be trained as an independent model.
- What evidence is sufficient to promote a research checkpoint into an Echo integration test.

**Guiding principle:** Build the smallest neural system that can demonstrate real learning, measure it honestly, and expand only when the evidence supports the next step.
