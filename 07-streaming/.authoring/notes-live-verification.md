# Streaming validator maintenance notes

Learner off-limits before attempting the tasks.

## Grading invariants

- Unsolved scaffolds must fail with NOT PASSED and exit 1; subprocess diagnostics are reduced to their final relevant line.
- Lag monitoring compares end offsets with committed offsets per partition and tests both no-alert and alert conditions.
- Transactional processing must preserve the exact expected sequence set after an injected process crash. The consumer disables auto-commit and the validator explicitly uses read_committed isolation.
- Capstone checkpoints compare database results with independent ground truth, including recovery and concurrent consumer rebalancing. Timeouts are execution bounds, not performance acceptance criteria.
- The Kubernetes bonus checks rendered resources with helm template and helm lint, including matching HPA targets and PDB selectors.

## Runtime considerations

Avoid concurrent full-corpus validator runs overloading the local broker. Derive transactional offsets from consumer positions and group metadata. Distinguish a worker-process crash from a database crash when reasoning about committed rows. Use the module's current configuration and validators for service versions, timeouts, and thresholds; runtime service state must be checked live.
