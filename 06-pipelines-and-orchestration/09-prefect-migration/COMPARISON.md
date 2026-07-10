# Airflow vs. Prefect — incremental price-record loader

Fill in each section with your own findings from porting the loader. Write
from what you actually observed running both, not from general reputation —
cite specifics (a command you ran, a log line, a config option you had to
set) wherever you can.

## Scheduling and backfill model

How does each tool decide when a run happens, and how does backfilling a
missed or historical date differ between them? What did you have to do
differently to backfill 2025-06-01 through 2025-06-14 in each?

## Failure handling and retries

Where do retries get configured in each, at what granularity (task vs.
whole-DAG/flow), and what happens to already-loaded partitions when a later
step in the same run fails? Did idempotency (or the lack of it) matter
differently in one tool than the other?

## Dev loop and testing

What was the actual iteration loop while writing each — editing, running,
inspecting a failure, fixing? Compare concretely: `airflow dags test` vs.
running `flow.py` directly, time-to-first-feedback, and how much
infrastructure each needs standing up before you can run anything at all.

## Operational footprint

What does each need running at rest for a production deployment (metadata
db, scheduler, webserver/UI, workers) versus what you actually needed for
this task? What would change if this pipeline had 50 DAGs/flows instead of
one?

## Where I'd use which

Given everything above, for what kind of pipeline would you reach for
Airflow, and for what kind would you reach for Prefect? Be specific about
what property of the pipeline drives that choice — don't just restate tool
reputations.
