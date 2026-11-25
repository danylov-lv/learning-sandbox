# SQL for Analytics lectures

This course assumes working knowledge of `SELECT`, `WHERE`, and basic joins.
By the end, you should be able to turn a reporting question into a sequence
of PostgreSQL 16 query stages, state what each row represents, and verify that
joins, time boundaries, and aggregation preserve the intended result. The
[module overview](README.md) describes the dataset, setup, and validators.
[SQL Optimization](../02-sql-optimization/README.md) follows this module and
covers execution plans and tuning.

## Chapter plan

The chapter numbers follow the prerequisites. The exercise map below identifies
the sections to read for each assignment.

| Chapter | Learning outcome and planned sections | Prerequisite reading | Status and path |
| --- | --- | --- | --- |
| [01. Row grain, joins, and aggregation](lectures/01-grain-joins-and-aggregation.md) | State the expected row key at each stage and check that a join or aggregate preserves the intended population. Sections cover row grain and join cardinality, counting and conditional aggregates, and checking query stages. | [Module overview](README.md) | Published |
| 02. Hierarchies and recursive CTEs | Map nodes to ancestors and summarize subtrees at a defined grain. Sections include *Fixed-depth self-joins*, *Walking a tree with a recursive CTE*, and *Structural leaves and subtree totals*. Cover anchor rows, termination, uneven depths, and nodes attached above the leaf level. | 01 | Planned, `lectures/02-hierarchies-and-recursive-ctes.md` |
| 03. Dates, timestamps, and time buckets | Define a reporting calendar and place boundary events in the intended hour, ISO week, or month. Sections include *Date and timestamp semantics*, *Half-open reporting intervals*, and *Time buckets and partial periods*. Use typed bucket keys and distinguish a bucket's calendar extent from its observed data. | 01 | Planned, `lectures/03-dates-and-time-buckets.md` |
| 04. Windows, ordering, and row selection | Choose a partition and ordering for neighbor comparisons, shares of totals, ranking, and selecting a single row per key. Sections include *Partitions and window order*, *Neighbors and totals*, and *Ranking and deterministic row selection*. Cover peer ties, filtering window results, `ROW_NUMBER`, `RANK`, `DENSE_RANK`, and PostgreSQL's `DISTINCT ON`. | 01 | Planned, `lectures/04-windows-and-row-selection.md` |
| 05. As-of joins | Match an event to the applicable version of a reference row while preserving event grain. Sections include *Equality and effective dates* and *Selecting and validating temporal matches*. Compare exact-date joins, `LATERAL` lookups, and selecting from candidate matches. Cover gaps, no eligible match, and rate conversion before aggregation. | 01, 03, and 04's row-selection section | Planned, `lectures/05-as-of-joins.md` |
| 06. Window frames and rolling statistics | Predict which rows contribute to a rolling measure on irregular data and explain its behavior with a short history. Sections include *Frame modes, peers, and boundaries*, *Rolling statistics*, and *Aggregating window results*. Cover `ROWS`, `RANGE`, `GROUPS`, default frames, and sample versus population standard deviation. | 03 and 04 | Planned, `lectures/06-window-frames-and-rolling-statistics.md` |
| 07. Coverage and missing observations | Build the expected reporting grid and distinguish a bucket with no events from a bucket with a measured zero. Sections include *Expected keys and dense time series* and *Missing rows, zero counts, and undefined ratios*. Cover series endpoints, left joins, and the denominator for a conditional share. | 01 and 03 | Planned, `lectures/07-coverage-and-missing-observations.md` |
| 08. Runs and gaps in ordered data | Define continuity for an ordered stream, group adjacent observations into runs, and summarize each run. Sections include *What breaks a run* and *Identifying and summarizing runs*. Compare transition flags with cumulative grouping and the row-number difference method on a separate example. | 04 and 06's frame section | Planned, `lectures/08-runs-and-gaps.md` |
| 09. Report measures and reconciliation | Build a multi-stage report with a defensible median, period-over-period change, and verifiable intermediate outputs. Sections include *Measurement grain and percentiles*, *Period comparisons and rounding*, and *Report checks by stage*. Cover observation weighting, continuous versus discrete percentiles, missing periods, and undefined changes. | 01–05 and 07's section on missing observations | Planned, `lectures/09-report-measures-and-reconciliation.md` |

## Exercise reading map

Each row links to published sections and names the reading still planned.
The exercise briefs contain the graded requirements.

| Practice | Reading and purpose |
| --- | --- |
| [01. Cross-source price spread](01-cross-source-price-spread/) | 01 [Row grain and join cardinality](lectures/01-grain-joins-and-aggregation.md#row-grain-and-join-cardinality) and [Counting and conditional aggregates](lectures/01-grain-joins-and-aggregation.md#counting-and-conditional-aggregates), then 02 *Fixed-depth self-joins*. Track the row key through the hierarchy and decide what each count measures. |
| [02. Category tree rollup](02-category-tree-rollup/) | 02 *Walking a tree with a recursive CTE* and *Structural leaves and subtree totals*, then 04 *Neighbors and totals* for the share-of-total subsection. Distinguish category counts from product counts and their denominators. |
| [03. Currency-normalized revenue](03-currency-normalized-revenue/) | 03 *Date and timestamp semantics* and *Time buckets and partial periods*, then 05 *Equality and effective dates* and *Selecting and validating temporal matches*. Distinguish the reference lookup date from the report's period key. |
| [04. Price change detection](04-price-change-detection/) | 04 *Partitions and window order* and *Neighbors and totals*. Interpret the previous observation within an irregular event sequence. |
| [05. Rolling price volatility](05-rolling-price-volatility/) | 06 *Frame modes, peers, and boundaries*, *Rolling statistics*, and *Aggregating window results*. Compare the input frames and account for undefined sample statistics. |
| [06. Top-N per group](06-top-n-per-group/) | 01 [Checking query stages](lectures/01-grain-joins-and-aggregation.md#checking-query-stages), 02 *Fixed-depth self-joins*, and 04 *Ranking and deterministic row selection*. Identify the grain of the input to ranking and choose how ties affect the selected rows. |
| [07. Time-bucketed trends](07-time-bucketed-trends/) | 03 *Time buckets and partial periods* and 01 [Counting and conditional aggregates](lectures/01-grain-joins-and-aggregation.md#counting-and-conditional-aggregates). Keep track of the population behind each measure within a week. |
| [08. Scrape coverage](08-scrape-coverage/) | 03 *Half-open reporting intervals* and both sections of 07. Check the expected report keys and what each kind of empty or observed bucket means. |
| [09. Gaps and islands](09-gaps-and-islands/) | 04 *Partitions and window order* and both sections of 08. Check whether the definition of continuity matches what the event stream can establish. |
| [10. Dedup latest snapshot](10-dedup-latest-snapshot/) | 04 *Ranking and deterministic row selection* and 01 [Checking query stages](lectures/01-grain-joins-and-aggregation.md#checking-query-stages). Verify row selection on tied inputs and check the grain after deduplication. |
| [11. Capstone pricing report](11-capstone-pricing-report/) | CP1 uses 03 for the time keys and 05 for temporal matches. CP2 uses 02 for ancestor mapping and 09 *Measurement grain and percentiles*. CP3 uses 04 *Neighbors and totals*, 07 for missing observations, and 09 *Period comparisons and rounding*. Use 09 *Report checks by stage* across all three checkpoints. |

## Documentation plan

- Keep the module README as the entry point for setup, seed size, task order,
  and validator commands. Keep the chapter status and reading guides here.
- Plan `docs/schema.md` as a compact reference for the five tables. Describe
  their grains, keys, relationships, timestamp types, and rate units. Identify
  which properties the database enforces and which come from the seed or a
  specific exercise. Link to the schema and post-load constraints for details.
- Keep task requirements and checkpoint instructions in their exercise briefs.
  Publish reusable explanations in the chapters. Use independent datasets with
  stated intermediate and final outputs, and add short self-checks where a
  boundary case or a misleading aggregate would otherwise be hard to spot.

## Verification and publication

Chapter 01's examples have been verified in PostgreSQL 16. Next to write is 03,
followed by 07, so the reading for the time-bucketed trends and scrape coverage
exercises is available early. Chapters 02–09 and the schema reference are
planned. Run each executable example in the module's PostgreSQL 16 environment
before publishing it.

- Check a timestamp exactly on a rolling frame's lower bound. PostgreSQL's
  offset `RANGE` includes the boundary, while exercise 05 describes an open
  lower bound. Reconcile the wording and grading contract before presenting
  them together. [PostgreSQL 16 window expressions](https://www.postgresql.org/docs/16/sql-expressions.html#SYNTAX-WINDOW-FUNCTIONS)
- Check hour boundaries, the stop argument of `generate_series`, and an ISO
  week crossing a calendar year. Use the module's `timestamp without time zone`
  type in examples and verify any comparison with `timestamptz` separately.
  [PostgreSQL 16 series functions](https://www.postgresql.org/docs/16/functions-srf.html)
  [PostgreSQL 16 date and time functions](https://www.postgresql.org/docs/16/functions-datetime.html)
- Test tied sort keys and a temporal lookup with a date gap and no eligible
  earlier reference row. Confirm the intended unmatched-row behavior before
  describing it in exercise reading guidance.
  [PostgreSQL 16 `SELECT`](https://www.postgresql.org/docs/16/sql-select.html#SQL-DISTINCT)
  [PostgreSQL 16 `LATERAL`](https://www.postgresql.org/docs/16/queries-table-expressions.html#QUERIES-LATERAL)
- Test percentile interpolation on an even-sized group, conversion to a type
  suitable for decimal-place rounding, and changes computed before and after
  rounding. Confirm which precision the capstone expects for its comparison.
  [PostgreSQL 16 aggregate functions](https://www.postgresql.org/docs/16/functions-aggregate.html#FUNCTIONS-ORDEREDSET-TABLE)
