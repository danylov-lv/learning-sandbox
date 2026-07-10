Approach, end to end:

1. `docker compose exec airflow-scheduler airflow backfill --help` — find
   the subcommand that starts a backfill run (something like `create`).
2. `docker compose exec airflow-scheduler airflow backfill <that-subcommand> --help`
   — read every flag. You're looking for: which DAG (its id,
   `t02_incremental_load`), a start-of-range date, an end-of-range date. There
   may also be flags about whether to re-run dates that already have
   successful runs — read what the default behavior is, since your repair
   pass targets dates you've deliberately emptied but Airflow's own run
   history for those dates still shows a prior success.
3. Run it once for the full 14-day range. Watch it work through each
   logical date; check the warehouse afterward (per-day row counts against
   `ground-truth.json`, `ops.load_audit` success rows).
4. Apply `src/repair.sql`. Re-check: the 3 days are now 0 rows in staging,
   the other 11 are untouched.
5. Run the backfill subcommand again, this time with the date range narrowed
   to only `2025-06-06`..`2025-06-08`. If the tool's default behavior skips
   dates it thinks already succeeded, look for whatever flag controls
   reprocessing/force behavior in that `--help` output — you want it to
   actually re-run those 3 dates, not skip them because a stale success
   record says they're fine.
6. Re-check the warehouse: all 14 days at correct counts, the 3 repaired
   days now showing 2 `success` audit rows instead of 1.
