# 08 — When ClickHouse, when DuckDB (writeup)

## Backstory

You've now loaded the same fact table — `price_history.observations`, years
of scraped (product, seller, time) price history — into three engines and
put each one under a real workload: Postgres as the OLTP baseline, a
ClickHouse `MergeTree` with a sparse primary index, materialized views,
`ReplacingMergeTree` dedup, and TTL lifecycle rules, and DuckDB querying a
Hive-partitioned Parquet lake with zero server process. Task 05 made you
measure Postgres against ClickHouse at 50M rows on the *exact same*
aggregate query. Task 07 made you measure DuckDB against ClickHouse on the
*exact same* lake. You have real numbers, not vibes.

Now a teammate is standing up analytics for a brand-new scraped dataset —
different domain, same shape of problem — and asks you the only question
that matters before anyone provisions anything: "Do we need a ClickHouse
cluster for this, or can I just point DuckDB at the Parquet files, or is
this small enough that Postgres is still fine?" Standing up a ClickHouse
server nobody needs is exactly as much of a mistake as running a 50M-row
aggregate through Postgres with no relevant index. Write the memo that
answers them honestly, citing the numbers you measured rather than the
reputations the tools have.

## What's given

- This module's task suite (01–07), which has taught you:
  - `01` — MergeTree tables and the sparse primary index: how `ORDER BY`
    prunes granules and what a query has to look like to benefit.
  - `02` — materialized views: pre-aggregating on write vs. aggregating on
    read, and what that costs at ingest time.
  - `03` — `ReplacingMergeTree`: dedup as a background merge process, not an
    immediate guarantee.
  - `04` — `TTL`: expiring or downsampling data automatically as it ages
    out, at the partition level.
  - `05` — Postgres vs. ClickHouse at 50M rows: the same per-category
    aggregate, one engine forced into a sequential scan, the other pruning
    via its primary index. You measured the ratio.
  - `06` — DuckDB reading a Hive-partitioned Parquet lake directly: no
    server, partition pruning from the directory structure alone.
  - `07` — DuckDB vs. ClickHouse head to head: same lake, same query, one
    engine embedded in your process, the other a server you had to keep
    running. You measured that ratio too, and its operational cost.
- A structured template (`ANSWER.md`) with five required section headings
  and guiding prompts under each — no answers filled in.
- `NOTES.md` for your post-task reflection.

## What's required

Fill in every section of `ANSWER.md` with real substance, grounded in what
you built and measured in tasks 01–07:

1. `## Where ClickHouse (server) earns its keep` — concrete criteria for
   when standing up a server is worth it: data volume where a sequential
   scan stops being viable, many concurrent readers hitting the same
   dataset, continuous ingest that benefits from materialized views doing
   the aggregation work at write time, a TTL/lifecycle policy that has to
   run automatically at scale, dashboards that need sub-second response
   under concurrent load.

2. `## Where DuckDB (embedded) is the right call` — ad-hoc or exploratory
   analytics, data that's already sitting on disk as files, a single
   analyst or a one-off script, no appetite for operating a stateful
   service, CI jobs and throwaway transforms where spinning up
   infrastructure would outlast the task itself.

3. `## Where neither — keep it in Postgres` — small enough data that a
   sequential scan is milliseconds anyway, workloads that need
   transactional freshness (read-your-writes, row-level updates) rather
   than analytical rollups, low enough query volume that adding a second
   engine is pure overhead with no payoff.

4. `## Three concrete calls` — three specific scenarios from your own
   scraping domain (pick your own: e.g. a new marketplace category feed, a
   nightly competitor-price export, an internal dashboard, a fraud/anomaly
   sweep). For each: state the decision (ClickHouse / DuckDB / Postgres)
   and justify it in one or two lines, citing the evidence you actually
   measured in tasks 05 and 07 (the benchmark ratios) rather than
   asserting it from first principles.

5. `## What surprised me` — at least one thing you measured in this module
   that changed a belief you walked in with (e.g. "I assumed ClickHouse
   would always win," or "I didn't expect DuckDB to be that close on a
   single-node read workload," or "the operational cost of TTL/materialized
   views was heavier/lighter than I expected").

Also fill in `NOTES.md`: what you learned, gotchas you hit, open questions
a real migration decision would still need answered.

## Completion criteria

From this task's directory:

```bash
uv run python tests/validate.py
```

The validator checks:
- `ANSWER.md` exists and contains all five required `## ` section headings
  (exact match).
- Each section is substantially filled with your own prose (at least ~250
  characters beyond the shipped guiding prompt) and no longer contains its
  `(fill in` placeholder marker.
- The "Three concrete calls" section is grounded in the module's own
  concepts — it must mention at least a couple of terms from: materialized
  view, TTL, ReplacingMergeTree, partition/pruning, ratio/benchmark.
- `NOTES.md` is filled beyond the template headers (at least ~200
  characters).
- On success: `PASSED` with a per-section character count. On failure:
  `NOT PASSED: <which section is empty or still a stub>`, exit 1, no
  traceback.

## Estimated evenings

1

## Topics to read up on

- OLAP server (ClickHouse) vs. embedded OLAP (DuckDB): where the line
  actually is
- The operational cost of a stateful service you have to run, patch,
  monitor, and back up, versus a library you `import`
- When materialized views and TTL lifecycle rules earn their complexity —
  and when they're solving a problem you don't have yet
- Concurrency and continuous ingest as the real ClickHouse differentiators
  (not "it's faster" — DuckDB is often plenty fast for one reader)
- DuckDB's sweet spot: files already on disk, a single process, no
  networked clients
- Data gravity: how much it costs to get data INTO an engine before you
  can even ask it a question

## `.authoring/` is off-limits

`.authoring/` holds spoilers for this module — full data contracts, RNG
draw order, ground-truth internals, and design rationale for every task.
Don't read it before finishing this task.
