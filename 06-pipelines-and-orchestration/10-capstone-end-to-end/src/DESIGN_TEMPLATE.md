# DESIGN

Copy this file to the task root as `DESIGN.md` and fill in every section
with your own reasoning, once CP1 and CP2 both pass. Bullets are prompts,
not a checklist — write prose, point at real numbers and real alerts from
this task, not generic Airflow-textbook answers.

## Pipeline topology

- The stage order you settled on (ingest / contract / core / silver /
  mart / summary) and any deviation from the module's suggested order,
  with why.
- Where the DAG fans out or stays linear, and why.

## Idempotency strategy

- Per stage: what makes re-running it for an already-loaded dt a no-op on
  the data, even though the task itself still executes.
- The one stage that was hardest to make idempotent, and what your first
  (wrong) attempt did instead.

## Contract strategy and evolution policy

- How v3 differs from your earlier contract(s), concretely.
- Your rule for "this failure rate means a schema changed" vs. "this is
  routine bad data" — the actual threshold or heuristic, and why you
  picked it.
- What happens to a record the contract rejects, end to end, from
  quarantine row to (if applicable) alert.

## Failure modes and recovery runbook

- At least two distinct failure modes you actually drilled (CP2) or
  reasoned through, and the exact recovery steps for each — what you'd
  type, in what order, referencing this DAG's task/stage names.
- How you know a scoped recovery didn't touch healthy partitions.

## Alerting policy

- What pages a human immediately vs. what only shows up in logs, and why
  that split.
- The three alert types this pipeline fires (contract_drift,
  quarantine_rate, dag_failure) — what each one's payload actually
  contains and who'd need to read it at 3am.

## What changes at 10x volume

- Which stage breaks first, and what in this design breaks it (spell out
  the actual bottleneck, not just "it would be slower").
- What you'd change first, and what you'd deliberately leave alone.
