# Module 07 — live verification notes (authoring, learner off-limits)

Record of what was actually run against the live stack, so a future session
trusts the module without re-deriving it. Two authoring sessions.

## Session 1 (prior): infra + tasks 01-05, 07, 09

- Stood up docker-compose (redpanda v24.3.5 + Postgres 16 + Console), verified
  healthy. Generated the corpus (seed 70707, ~200k events, ~2% late) and
  committed `data/ground-truth.json`.
- Built `harness/common.py`, the module README, CONVENTIONS ports.
- Generated tasks 01-05, 07, 09. Pass-paths for 04 and 07 were verified with
  throwaway reference impls (scratch-t04/, scratch-t07/) — those scratch dirs
  were left on disk at session end and deleted in session 2.

## Session 2 (this): tasks 06, 08, 10, k8s-bonus

Generated via subagents (Sonnet), each verifying its own work live before
returning. Broker load was staggered: 06 + 08 in parallel, then 10 alone
(three full-corpus validators at once on the single-smp broker is too much),
k8s-bonus alongside (no broker).

Stock-fail (all): every validator turns the stub's `NotImplementedError` into
a clean `NOT PASSED`, exit 1, surfacing only the last output line (a
`_last_line()` helper avoids leaking the subprocess traceback tail).

Pass-paths, proven live with throwaway references in gitignored `scratch-*/`
(all deleted afterwards; stubs restored):

- **06 lag-monitoring** — two-phase deterministic validator: commit group
  offsets == end offsets (lag 0, no alert), then produce a second batch so
  high advances while committed stays (lag 100000 across 6 partitions, alert
  fired at threshold 50000). Per-partition rows compared against an
  independent `end_offsets - committed_offsets` recompute.
- **08 kafka-transactions-eos** — read-process-write with a transactional
  producer, `send_offsets_to_transaction`, batch commits (BATCH_SIZE=5000).
  Injected a mid-transaction crash at 70000; a `read_committed` drain of the
  output topic then showed `seq` set == `{0..199999}` exactly — no loss, no
  duplicates = topic-to-topic exactly-once. (librdkafka defaults to
  read_committed, but the validator sets isolation.level explicitly.)
- **10 capstone** — one `pipeline.py` folds category totals (EOS via
  dedup-on-seq), event-time windows, and latest-price (last-write-wins by
  seq) into Postgres in one txn/message; `monitor.py` snapshots lag. CP1
  (clean run) and CP2 (injected crash + two concurrent instances forcing a
  rebalance + final run) both reproduce ground truth EXACTLY; CP3 checks
  DESIGN.md then re-runs CP1/CP2.
- **k8s-bonus** — offline helm validator: `helm template` + `helm lint`
  render a Deployment (resource-bounded), an autoscaling/v2 HPA targeting it,
  and a PDB whose selector matches the Deployment's pod labels.

## Orchestrator review fixes applied after subagents returned

- Capstone timeouts were gating a *correct* solution on wall-clock: a naive
  per-message four-execute+commit path measured ~445s here, over the original
  CP1 360s limit. Per the SPEC "timing varies by machine — prefer structural
  checks" rule, correctness is graded on the exact ground-truth match, not the
  clock. Raised CP1 360->900s, CP2 rebalance 420->900s, CP2 final 300->600s,
  and reframed the `pipeline.py` performance note + `hint-3.md` from "the
  timeout will fire" to throughput advice. The writeable-CTE +
  `SET synchronous_commit TO off` fast path (~191s) stays as optional guidance.
- Added `pyyaml>=6.0.2` to `pyproject.toml` (k8s-bonus validator parses
  rendered YAML; the module had no yaml provider). `uv.lock` synced.

## Stock state at session end

No `scratch-*/` dirs, no reference solutions, no `DESIGN.md` tracked; every
`src/` scaffold retains its `NotImplementedError`. The docker stack was left
running — `docker compose down -v` if a cold stock state is wanted.

## Empirics worth keeping

- confluent-kafka `send_offsets_to_transaction` wants
  `consumer.position(consumer.assignment())` + `consumer.consumer_group_metadata()`;
  the consumer must NOT auto-commit, or the EOS guarantee is undermined.
- Per-message Postgres commits do not scale to 200k events; a single
  writeable-CTE statement per message plus `synchronous_commit off` is ~2.3x
  faster (445s -> 191s) with no correctness change (the crash hook is a process
  crash, so committed rows stay durable in the still-running server).
- Two same-group pipeline instances never contend on `core.t10_latest_price`
  (per-key ordering keeps a product in one partition); category/window rows
  serialize harmlessly via Postgres row locks on ON CONFLICT DO UPDATE.
