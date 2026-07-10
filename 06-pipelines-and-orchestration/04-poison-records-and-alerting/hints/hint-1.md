# Hint 1

Three separate things trip people up here, and it pays to keep them apart in your head:

1. Getting the day into the task. The DAG has `schedule=None`, but `airflow dags test <dag_id> <date>` supplies a logical date, and Airflow's usual templating machinery works with it. Look at how a TaskFlow-decorated function can receive templated values, or how a task can reach its own run context.

2. Classification vs loading. Write and unit-sanity-check `classify_line` in isolation first (it's a pure function — feed it a handful of lines from a real file by hand). Only then wire it into the ingest task. If you interleave "is this line bad" with "insert row" from the start, every bug looks like a database bug.

3. Idempotency is two different problems in disguise. Staging has a primary key, so the database can help you there. Quarantine has only a `bigserial` — the database will happily accept the same rows twice. Reread how your rerun scenario actually behaves before assuming it works.

Also: the failure scenario (2025-06-16) is only a scenario if a missing file makes the task raise. Check what your file-reading code does when the directory doesn't exist — an empty glob that yields zero lines is a silent success, which is exactly the failure mode this task exists to kill.
