# Learning path and verification

The learner starts with joins, CTEs, and keys. PostgreSQL, schema creation,
connection setup, and worker coordination are supplied. Each task starts
with its own schema. SQL can be developed from the first task without
implementing a loader or a scheduler.

| Task | Progression and validator evidence |
|---|---|
| 01 | Write one observation at a time. Exact returned rows and untouched neighbors test composite-key scoping. |
| 02 | Combine two writes. A callback checks visibility on an independent session and forces rollback between writes. |
| 03 | Add a partial recovery boundary. PostgreSQL notices prove the invalid inserts were attempted. The caller keeps ownership of the surrounding transaction. |
| 04 | Add duplicate and late delivery. SQL observations show both upserts. History and current price are checked separately after each commit. |
| 05 | Change input to CSV. The checks observe COPY and set-based staging merges, then exercise replay, late input, and a malformed integer. |
| 06 | Read across a concurrent transaction. Three synchronized reads distinguish uncommitted changes and snapshot lifetimes. |
| 07 | Control concurrent writes. A fixed interleaving forces PostgreSQL to report a deadlock. The corrected interleaving observes a blocked worker and two committed adjustments. |
| 08 | Protect a cross-row invariant. Real write skew and serialization errors test fresh reads, the attempt budget, and propagation of unrelated constraint errors. |
| 09 | Combine atomic writes, replay rules, and staging. Checkpoint 1 verifies commit and rollback. Checkpoint 2 adds two concurrent ingestion cases and checks the ledger and both price tables against the CSV files. |

## Verification results

- All nine stock validators produced the expected scaffold failure with exit code 1.
- All nine accepted temporary working submissions on PostgreSQL 16.10 in
  Docker, including both capstone checkpoints. Ten deliberately faulty
  submissions were rejected for their intended reasons. Temporary
  submissions were kept outside the repository.
- Tasks 07, 08, and 09 passed four additional runs each of their concurrent
  scenarios. Concurrency assertions measure server state and committed rows.
  Harness timeouts bound stalled tests.
- The deterministic generator produced identical files on repeated default
  runs. The capstone CLI initialized its schema, loaded both generated
  batches, and reported the first batch as already applied on replay.
- Module CI passed its scaffold, no-solution, lockfile, and healthy-service
  checks. The repository guards and CI metadata validator passed.
- Validation covers one PostgreSQL primary, application fault injection, and
  independent sessions. Replication, database-server crashes, and external
  delivery or acknowledgements are outside the local setup.
