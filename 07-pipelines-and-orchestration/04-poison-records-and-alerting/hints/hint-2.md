# Hint 2

Concrete mechanisms for each piece:

**Day into the task.** With TaskFlow, arguments you pass when calling the task in the DAG body are template-rendered — so calling your task with the string `"{{ ds }}"` hands it `2025-06-05` at run time. Alternatively `from airflow.sdk import get_current_context` inside the task gives you the context dict with the logical date.

**Idempotent staging.** `INSERT ... ON CONFLICT (dt, line_no) DO NOTHING` (or `DO UPDATE` if you want reruns to refresh `payload`). Either satisfies the validator; pick one deliberately.

**Idempotent quarantine.** The standard pattern for a keyless append table: inside one transaction, `DELETE FROM ops.quarantine WHERE dt = %s` and then insert the day's rows fresh. The transaction matters — if the insert fails halfway, the delete must roll back with it, or a crashed rerun leaves you with *less* data than before.

**Batching.** ~50k lines per day means ~50k inserts. `cursor.executemany` in psycopg 3 pipelines nicely; `COPY` (via `cursor.copy`) is even faster for staging. A per-row `execute` + commit will take minutes and make you hate the rerun scenario.

**jsonb.** psycopg 3 does not automatically adapt a Python dict to jsonb — wrap it (`psycopg.types.json.Jsonb(record)`) or pass the already-serialized string and cast in SQL (`%s::jsonb`).

**Failure callback.** `on_failure_callback` on the `@dag` decorator receives a context dict; `context["dag"]`, `context["run_id"]`, and the logical date are all in there (poke at the keys with a debug `print` on a forced failure). POST with stdlib `urllib.request` exactly like `dags/smoke_env.py` does — the callback should not depend on your task code having worked.

**Rate task placement.** The rate check needs the counts from ingest. Return a small dict from the ingest task and take it as a parameter in the rate task — that's the whole XCom story for this DAG. Counts, not record lists.
