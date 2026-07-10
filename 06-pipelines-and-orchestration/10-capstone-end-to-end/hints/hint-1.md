# Hint 1

You already have working pieces from tasks 01-07: an ingest task that
separates malformed lines from parseable ones, a contract check that
routes bad records to quarantine, a core loader, and (from the Spark
task) code that reads/writes parquet against `s3a://lake-06/...`. This
capstone is mostly integration work, not new algorithms — the hard part is
making the *composition* idempotent end to end, not any single stage.

Before writing a single line of the DAG, write down, per stage, what
"already done for this dt" looks like in the data (a row count, a
partition's existence, a max timestamp) and what your task needs to check
or overwrite to make re-running safe. Do this on paper first. A DAG that
works once and breaks on the second run of the same day is not partially
done — it's a different, harder bug to find later once three more stages
depend on it.

Think about where `dt` (the day partition) needs to be threaded through
every single task, and how Airflow's templating/logical_date maps to the
`YYYY-MM-DD` strings the rest of this module's contract uses.
