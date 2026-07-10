# Hint 2

Concrete mechanisms per stage, if you're stuck on the idempotency design:

- **Staging**: the table's PK is (dt, line_no). A re-run for a dt either
  deletes that dt's staging rows first and re-COPYs, or upserts on the PK.
  Either works; mixing them ("insert and hope") does not.
- **Core**: the unique key (source_site, product_url, scraped_at) plus
  `INSERT ... ON CONFLICT DO NOTHING` (or DO UPDATE, if you want re-runs
  to refresh loaded_at — but think about what CP2's "unaffected days'
  loaded_at unchanged" check implies about that choice for scoped
  recovery).
- **Quarantine**: this one is easy to get wrong — a re-run that
  re-quarantines the same malformed lines doubles the quarantine rows and
  skews your quarantine-rate alert. Delete-by-(dt, stage) before
  re-inserting, inside the same transaction as the insert.
- **Silver lake**: Spark's `mode("overwrite")` on the *partition path*
  (write directly to .../dt=<day>/, not to the table root with
  partitionBy) replaces exactly one day's partition and nothing else.
- **Mart**: the PK is (dt, category, currency) — upsert, or
  delete-where-dt then insert in one transaction.

For the contract-drift detection heuristic: you know your quarantine
reasons. If one single reason accounts for the overwhelming majority of a
day's contract failures AND the failure rate is far above the historical
baseline (~1-2%), that's drift, not noise. Pick actual numbers and write
them down for the CP3 writeup.

For CP2's scoped recovery: `airflow dags test t10_capstone <date>` runs
one day. Three days is three invocations (or a bounded `airflow dags
backfill`). The trap is a DAG whose ingest/core stages rewrite data even
when nothing changed — if your core upsert bumps loaded_at on conflict,
recovering day X will touch day X's core rows (fine) but a "recover
everything to be safe" full backfill will touch all 14 days' loaded_at
and fail the validator (that's the point).
