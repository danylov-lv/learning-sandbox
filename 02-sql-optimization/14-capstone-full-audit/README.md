# 14 — Capstone: Full Database Audit

## Backstory

You've spent the last several weeks firefighting individual slow queries in
the Kupitron marketplace database, one ticket at a time — account pages,
support dashboards, search, ops queues. It worked, but it was reactive:
someone screamed, you found the one query, you fixed it. Now management
wants something else: a systematic audit of the whole inherited database,
the kind of write-up a senior engineer hands to a team so nobody has to
rediscover the same defects one screaming ticket at a time.

You'll produce four things: a written optimization report, a prioritized fix
plan, the fixes actually applied, and basic hygiene restored. This is a
multi-evening capstone — work it in three checkpoints, each with its own
validator.

## Starting from a fresh database

**Before you start, reset the database to its stock, fully-defective state:**

```
docker compose down -v
docker compose up -d
uv run python seed/generate.py
```

**This destroys any fixes you applied in earlier tasks (01-13) on this same
database.** That's intentional — this capstone audits the database as if you
were seeing it for the first time, with nothing already patched. If you want
to keep an earlier task's working state for reference, do that *before*
running the commands above; there's no undo once `down -v` has dropped the
volume.

## What's given

- The same live Postgres 16 instance the rest of this module uses, at
  `localhost:54302` (db/user/pass: `sandbox`), container
  `02-sql-optimization-postgres-1` — now reset to stock.
- `../seed/schema.sql` — the schema, with its defect comments. Read it.
- `../tools/plan_check.py`, `../tools/baseline.py` — the same libraries used
  throughout this module.
- `workload/qc01.sql` through `workload/qc08.sql` — eight queries, each
  representing a real feature of the Kupitron app, each with a header
  comment stating the feature it serves and its SLA. These are **given** —
  don't rewrite the query text itself; your job is to make the database
  serve them within their stated SLA, by whatever combination of indexing,
  statistics, and schema changes you judge appropriate.
- `REPORT_TEMPLATE.md` — copy this to `REPORT.md` in this same directory and
  fill it in as you go. Its section headings are load-bearing — the
  checkpoint validators look for them by number.

## What's required

### CP1 — Diagnose and baseline

For every query in `workload/`, run `EXPLAIN (ANALYZE, BUFFERS)`, find the
worst plan node, and record a machine-local timing baseline:

```
uv run python tools/baseline.py record 14-capstone-full-audit/workload/qc01.sql --id qc01
```

(repeat for qc02..qc08). Then start `REPORT.md` from the template: fill in
section 1 (inventory), section 2 (one triage row per query — baseline
median, worst plan node, your suspected root cause), section 3 (which
defect family affects which queries), and section 4 (a prioritized fix
plan).

**Completion criteria:**

```
uv run python 14-capstone-full-audit/tests/check_cp1.py
```

This only checks completeness (every qc id has a baseline and a triage row,
sections 1-4 exist) — it cannot grade whether your diagnosis is *correct*.
That's on you; the next checkpoint will tell you if you were wrong.

### CP2 — Fix the hot paths

Apply fixes directly against the live database (DDL, `ANALYZE`, whatever the
defect calls for) until every workload query's plan looks structurally
sound and its timing clears its SLA with room to spare. Some queries accept
more than one valid fix family — read each query's SLA and think about what
"clearly meets it" means before committing to one approach.

**Completion criteria:**

```
uv run python 14-capstone-full-audit/tests/check_cp2.py
```

Per query, this checks a structural plan gate and (except where noted in the
checker's own comments — some queries gate on plan shape alone) a relative
speedup against your CP1 baseline. Update `REPORT.md` section 5 with what
you actually did and the before/after median for every query.

### CP3 — Hygiene and report

Clean up what's left: vacuum debt, stale statistics, redundant indexes.
Finish `REPORT.md` sections 6-8 (hygiene, type-hygiene analysis, remaining
risks — no migration required for section 7, analysis only).

**Completion criteria:**

```
uv run python 14-capstone-full-audit/tests/check_cp3.py
```

## Estimated evenings

2-4

## Topics to read up on

- Reading an index census (`pg_indexes`) against a real workload, not in
  the abstract
- `pg_stat_user_tables`, `n_dead_tup`, and what `autovacuum_enabled = off`
  actually costs you over time
- `pg_stats` staleness vs. statistics target — when `ANALYZE` alone fixes a
  bad estimate and when it doesn't
- Table partitioning (`PARTITION BY RANGE`) as an alternative to indexing for
  time-series retention/recency queries, and its tradeoffs
- Prioritizing a fix backlog: structural severity vs. how many workload
  queries a single fix resolves at once
- Why a query can get *slower*, not faster, after a statistics refresh, and
  what that says about cost-based query planning

## A note on `.authoring/`

`../.authoring/tasks-w4-capstone.md` documents this task's defect mapping,
measured numbers, and gate calibration in full. It's there for whoever
maintains this module later — reading it before you've done the audit
yourself would defeat the point of the exercise.
