Two different operational events look superficially similar and are not:
"we haven't loaded history yet" and "history is loaded but a chunk of it is
now wrong or missing." Airflow's backfill machinery is built to run a DAG
across a range of logical dates it wouldn't otherwise run for on its own —
that's the shared mechanism underneath both. What differs is the range you
give it. Don't reach for "delete everything and reload all 14 days" as your
repair strategy just because it's simpler to reason about — the whole point
of this drill is repairing 3 days without disturbing the 11 that are fine.

Before touching the CLI, go check what Airflow 3 actually calls this
subcommand now. If you remember `airflow dags backfill` from an older
version or a tutorial, that memory is exactly the thing to distrust here —
verify against the pinned image, not against what you recall.
