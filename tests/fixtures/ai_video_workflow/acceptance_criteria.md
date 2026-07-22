# Acceptance Criteria

The minimal prototype is successful only if:

- Every stage writes an explicit success or failure record.
- Every stage output can be traced to the fixture script and placeholder assets.
- Missing external tools fail with a named missing dependency.
- Cost-bearing or internet-dependent stages are skipped or marked `requires_external_service`.
- The workflow can resume from the last successful stage by reading the stage manifest.
- Human review points are recorded before final render and before any publishing/export handoff.
- The final file, if produced, is a short local test segment, not a buyer deliverable.
