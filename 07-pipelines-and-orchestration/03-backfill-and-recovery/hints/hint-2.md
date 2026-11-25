`airflow backfill --help` (inside any Airflow container) lists its own
subcommands; one of them creates a backfill run. Its `--help` in turn shows
you the flags you need: which DAG to run it for, and a start/end of the date
range (the exact flag names are for you to read off `--help` in the pinned
3.1.0 image — do not guess the spelling). You need it twice with different
ranges:

- The initial pass: the full range, `2025-06-01` through `2025-06-14`.
- The repair pass: only `2025-06-06` through `2025-06-08`.

Both invocations target the same DAG, `t02_incremental_load`. The DAG
doesn't need to change between the two calls — it's already idempotent, so
running it again for `06-06`–`06-08` (whether or not you'd already deleted
those rows) is safe, and the point of deleting them first is just to prove
the repair is doing real work, not to make the repair "necessary" in some
stricter sense.

Watch the backfill's own output/logs for confirmation each date's run
succeeded before moving on — don't assume it worked just because the command
returned.
