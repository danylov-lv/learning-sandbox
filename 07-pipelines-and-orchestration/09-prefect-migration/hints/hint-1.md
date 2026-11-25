# Hint 1

Start from the loading semantics, not the Prefect decorators — you already
solved "read a day's ndjson, skip what doesn't parse, load the rest
idempotently" in task 02. The only genuinely new part here is where
`@task`/`@flow` go and how retries are configured; the parsing and upsert
logic should look familiar.

Run with a tiny, deliberately wrong version first (e.g. tasks that just
return counts without touching the DB) to confirm the flow executes
end-to-end and the CLI argument reaches the flow function, before wiring in
the real Postgres calls.
