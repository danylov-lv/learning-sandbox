Think about what "the day to load" actually means for a DAG that has no
fixed schedule. You trigger it manually, but you still pass a date when you
run `airflow dags test t01_raw_to_staging 2025-06-01` — that date becomes the
run's logical date, and Airflow exposes it to your task through context, not
through a function argument you invent yourself. Go find out how a
`@task`-decorated function in the Airflow 3 TaskFlow API gets at context —
there is more than one way, and the module's `smoke_env.py` DAG doesn't need
context at all, so it won't show you the pattern. Read Airflow's docs on
context access inside TaskFlow tasks before writing anything.

Separately: think about what "stable line_no" buys you. If you renumbered
only the lines that parsed, rerunning this DAG after the raw file format
changes upstream (or after you fix a bug in your own parsing) could silently
shift every row's `line_no`. Number by position in the file you actually
read, before you decide whether a given line is any good.
