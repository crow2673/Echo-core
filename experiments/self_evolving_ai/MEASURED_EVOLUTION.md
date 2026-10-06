# Measured Evolution

v0.5 closes an important gap in the earlier prototype.

The organism may propose and build a candidate, but a candidate is not an
improvement merely because a model says it is better.

The measured path is:

1. Build candidate.
2. Run the static safety inspection.
3. Execute the candidate through a narrow evaluate(payload) contract.
4. Run the same deterministic cases against the baseline.
5. Compare numeric scores.
6. Promote only when the candidate beats the baseline.
7. Record the decision, scores, reason, and candidate hash in an append-only journal.
8. Keep rollback available through the existing promotion gate.

The candidate runner is an execution boundary, not a security sandbox.
Static inspection is still required, and stronger OS-level isolation is a
future hardening step.

This gives the project a concrete path from:

"I think I improved" -> "I measured an improvement" -> "I adopted it."
