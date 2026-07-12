# Progress

Flat checklist of all tasks across all modules. Checkboxes are ticked as tasks are completed by the learner. Task lists are populated when each module is generated; until then, a placeholder line stands in.

## 01-sql-foundations

- [ ] 01-cross-source-price-spread — price spread by root category and source tier
- [ ] 02-category-tree-rollup — recursive category-tree rollup
- [ ] 03-currency-normalized-revenue — currency-normalized monthly revenue
- [ ] 04-price-change-detection — consecutive-snapshot price-drop detection
- [ ] 05-rolling-price-volatility — 30-day RANGE-framed rolling volatility
- [ ] 06-top-n-per-group — top-3 products per level-2 category
- [ ] 07-time-bucketed-trends — weekly trend bucketing with distinct counts
- [ ] 08-gaps-and-islands — longest out-of-stock streaks
- [ ] 09-dedup-latest-snapshot — dedup to latest snapshot per pair
- [ ] 10-capstone-pricing-report (capstone)
  - [ ] CP1: as-of converted monthly base
  - [ ] CP2: rollup to root category + median
  - [ ] CP3: month-over-month window + final shape

## 02-sql-optimization

- [ ] 01-read-the-plan — diagnose and fix a 6M-row order-lookup query via EXPLAIN
- [ ] 02-support-dashboard — range-predicate customer-summary aggregate
- [ ] 03-order-detail-join — fix a misordered composite index on order_items
- [ ] 04-index-only-scan — covering index for a heap-free order-list query
- [ ] 05-jsonb-containment — GIN index for JSONB brand-attribute containment
- [ ] 06-trigram-search — pg_trgm index for leading-wildcard title search
- [ ] 07-planner-blindspots — fix a stale-statistics-driven bad plan
- [ ] 08-index-audit-reviews — drop redundant indexes against a documented workload
- [ ] 09-deep-pagination — keyset rewrite of a deep OFFSET/LIMIT page
- [ ] 10-partition-the-firehose — monthly RANGE partitioning for inventory_events
- [ ] 11-vacuum-debt — remediate vacuum debt on three never-vacuumed tables
- [ ] 12-worker-lock-queue — SKIP LOCKED claim query for parallel workers
- [ ] 13-kill-the-n-plus-one — constant-query rewrite of a dashboard fetch
- [ ] 14-capstone-full-audit (capstone)
  - [ ] CP1: diagnose and baseline
  - [ ] CP2: fix the hot paths
  - [ ] CP3: hygiene and report

## 03-data-modeling

- [ ] 01-relational-core — normalized OLTP schema for shops/products/listings/observations + loader
- [ ] 02-scd2-history — SCD2 history for shop name/tier and product brand/category
- [ ] 03-star-schema — Kimball star schema in `mart` with SCD2 dims + as-of load-time resolution
- [ ] 04-capstone-bitemporal (capstone)
  - [ ] CP1: late-arriving data and bitemporality
  - [ ] CP2: lifecycle + client questions, full 16-question battery green
  - [ ] CP3: design writeup

## 04-storage-and-formats

- [ ] 01-format-shootout — JSONL vs CSV vs Parquet size and scan-time shootout
- [ ] 02-compression-codecs — snappy/gzip/zstd hot-tier and archive-tier codec choice
- [ ] 03-row-groups-and-pushdown — row-group size and sort order for predicate pushdown
- [ ] 04-partitioned-datasets — hive-partitioned lake vs a high-cardinality partition trap
- [ ] 05-minio-object-store — lake upload to MinIO and LIST/GET cost of small files
- [ ] 06-delta-lake — Delta Lake commits, schema evolution, compaction, and time travel
- [ ] 07-duckdb-taste — DuckDB SQL over the partitioned Parquet lake with pruning proof
- [ ] 08-capstone-lake-layout (capstone)
  - [ ] CP1: pipeline — bronze/silver medallion build from raw JSONL
  - [ ] CP2: quality gates — codec, file count/size, row-group pruning, smoke query
  - [ ] CP3: design memo — layout defended with measurements from tasks 01-07

## 05-distributed-processing-spark

- [ ] 01-lazy-plans-and-explain — lazy evaluation, actions vs transformations, reading `explain()`
- [ ] 02-partitions-and-shuffles — `repartition` vs `coalesce`, `spark.sql.shuffle.partitions`, skew + salting
- [ ] 03-joins-broadcast-vs-smj — broadcast vs sort-merge joins, AQE runtime conversion
- [ ] 04-udfs-and-arrow — python UDF vs `pandas_udf` vs built-ins, measured
- [ ] 05-windows-at-scale — window functions, top-n per source, window vs pre-aggregate
- [ ] 06-parquet-to-minio-s3a — partitioned Parquet on object storage, partition pruning
- [ ] 07-polars-calibration — same job in polars vs Spark, when Spark is overkill
- [ ] 08-capstone-scrape-lake (capstone)
  - [ ] CP1: pipeline — raw dumps to enriched silver lake on MinIO
  - [ ] CP2: shuffle tuning — naive vs tuned job, measured in the Spark UI
  - [ ] CP3: design memo — DESIGN.md defended with measurements, incl. the polars verdict

## 06-pipelines-and-orchestration

- [ ] 01-first-dag-raw-to-staging — first Airflow DAG: raw NDJSON to `staging`, skipping malformed lines
- [ ] 02-incremental-idempotent-loads — `@daily` schedule, idempotent partition loads, one audit row per run
- [ ] 03-backfill-and-recovery — full + scoped backfill, recover a deleted range without duplicates
- [ ] 04-poison-records-and-alerting — classify and quarantine malformed/invalid records, alert on degradation
- [ ] 05-contract-gate-pandera — pandera schema as a boundary contract, route violations to quarantine
- [ ] 06-contract-evolution — catch additive + type-change drift, evolve the schema without breaking downstream
- [ ] 07-spark-stage-silver-lake — orchestrate the module 05 Spark job as a stage, write a partitioned silver lake to MinIO
- [ ] 08-dbt-marts-over-oltp — dbt staging views + daily-GMV marts over module 02's OLTP Postgres, tests and incremental stability
- [ ] 09-prefect-migration — port the incremental load to Prefect + written Airflow-vs-Prefect comparison
- [ ] 10-capstone-end-to-end (capstone)
  - [ ] CP1: build + full backfill — all 14 days through quarantine + contract gate into `core`, contracts green
  - [ ] CP2: failure drills — recover a half-dead midstate without duplicates, handle a fresh unannounced drift
  - [ ] CP3: design memo — DESIGN.md defended end-to-end, CP1+CP2 still green
- [ ] k8s-bonus (optional) — package the loader as a hand-written Helm chart (CronJob, Deployment, PDB) on kind/k3d

## 07-streaming

- [ ] 01-log-vs-queue-and-offsets — publish the price stream; two consumer groups each read the full log independently; history re-read from offset 0
- [ ] 02-delivery-semantics — manual offset commits: at-most-once vs at-least-once; survive an injected mid-stream crash with zero loss
- [ ] 03-consumer-groups-rebalancing — partition assignment across a group; trigger a rebalance and observe reprocessing/reassignment
- [ ] 04-exactly-once-into-postgres — at-least-once + idempotent dedup/offset in one Postgres txn = exactly-once aggregate across two crashes
- [ ] 05-windowed-aggregation — event-time 15-min tumbling windows per category, correct late-event assignment
- [ ] 06-lag-monitoring — compute per-partition lag (high watermark minus committed), snapshot to Postgres, alert past a threshold under a burst
- [ ] 07-compacted-topics — compacted topic for latest-state; materialize a current-price table matching last-write-wins by seq
- [ ] 08-kafka-transactions-eos — transactional read-process-write between topics; exactly-once proven via a read_committed drain across a mid-txn crash
- [ ] 09-rmq-vs-kafka-writeup — written: which parts of a production RMQ pipeline benefit from Kafka, which don't, why
- [ ] 10-capstone-streaming-pipeline (capstone)
  - [ ] CP1: steady pipeline — exactly-once category totals + event-time windows + latest-state, all matching ground truth on a clean run
  - [ ] CP2: chaos consistency — same tables still exact after an injected crash and a two-instance rebalance; lag snapshot recorded
  - [ ] CP3: design memo — DESIGN.md defended, CP1+CP2 still green
- [ ] k8s-bonus (optional) — deploy the consumer as a Deployment with HPA + PDB on kind/minikube; scale replicas and watch the group rebalance

## 08-cdc-debezium

- [ ] 01-connector-setup-snapshot-vs-streaming — register a Debezium Postgres connector; prove the snapshot phase (op=r per existing row) hands off to streaming (op=c/u/d) from the event stream alone
- [ ] 02-change-event-anatomy — decode the full envelope: schema vs payload, the source block, and the base64 Kafka Connect Decimal encoding of NUMERIC prices under decimal.handling.mode=precise
- [ ] 03-updates-and-deletes-downstream — apply before/after diffs and delete tombstones to a downstream replica table so it mirrors the source after an update/delete burst
- [ ] 04-schema-evolution — add a column on the source without breaking a running connector or consumer; the replica keeps converging across the schema change
- [ ] 05-replica-lag-and-alerting — measure replication-slot lag (bytes and time) and alert past a threshold under a change burst; understand the orphaned-slot WAL-pinning hazard
- [ ] 06-exactly-once-materialization — LSN/offset-ordered idempotent upsert into the mart so redelivery/restart can't corrupt state (continuation of module 07 task 04)
- [ ] 07-cdc-vs-rescraping-writeup — written: where CDC beats periodic re-scraping/re-querying and where it's overkill
- [ ] 08-capstone-converge (capstone)
  - [ ] CP1: steady replica — full source→Debezium→mart pipeline converges (mart == source) after a scripted insert/update/delete burst on a clean run
  - [ ] CP2: chaos convergence — mart still converges to source after an injected mid-run crash and connector restart (redelivery survived)
  - [ ] CP3: design memo — DESIGN.md defended, CP1+CP2 still green

## 09-olap-clickhouse-duckdb

- [ ] 01-mergetree-and-primary-index — ORDER BY as a sparse primary index; prove part/granule pruning via `system.query_log` read_rows (pruned scan << full scan)
- [ ] 02-materialized-views — incremental MV rollup (SummingMergeTree) maintaining daily-per-category count+price_sum as rows stream into a landing table
- [ ] 03-replacingmergetree-dedup — ReplacingMergeTree(version) + FINAL/argMax to keep the latest row per natural key without waiting on background merges
- [ ] 04-ttl-and-lifecycle — table TTL DELETE for retention (15-month window); force it with OPTIMIZE FINAL / MATERIALIZE TTL and verify the surviving split
- [ ] 05-postgres-vs-clickhouse-50m — the same per-category in-stock analytics on a row store vs a columnar engine; correctness gate + machine-local relative timing baseline
- [ ] 06-duckdb-on-parquet — DuckDB querying the Hive-partitioned Parquet lake directly (zero server); correctness + partition pruning to a single file
- [ ] 07-duckdb-vs-clickhouse — same analytical query, running server vs embedded engine; correctness + cross-engine agreement + relative timing
- [ ] 08-when-clickhouse-when-duckdb — written: decision framework for when a ClickHouse server, when DuckDB on a laptop, and when neither (keep it in Postgres)
- [ ] 09-capstone (capstone)
  - [ ] CP1: ClickHouse serving layer — incremental MV rollup + business questions (price_sum, per-category in-stock, top sellers) all match ground truth
  - [ ] CP2: DuckDB cross-check — the same business questions answered over the Parquet lake reproduce ground truth (and thus agree with CP1), partition pruning proven
  - [ ] CP3: design memo — DESIGN.md defended (ORDER BY, MV vs on-demand, lifecycle, server-vs-embedded), CP1+CP2 still green

## 10-nosql-patterns

- [ ] 01-rate-limiter — per-domain requests/window cap via a single atomic Redis check-and-record, closing the check-then-act race that lets a burst of workers blow past the limit
- [ ] 02-distributed-lock — fleet-wide single-owner lock: token-checked safe release plus a fencing token so a worker stalled past its TTL can't corrupt state after another worker takes over
- [ ] 03-dedup-filter — exact Redis SET vs Bloom filter for "have I seen this url": exactness/zero-false-negatives vs a fixed tiny memory footprint traded for a bounded false-positive rate
- [ ] 04-redis-streams-consumer — consumer group with PEL tracking, XACK, and XAUTOCLAIM reclaim so a dead worker's in-flight entries get taken over without double-claiming a still-alive worker's work
- [ ] 05-mongodb-document-modeling — model heterogeneous scraped products as documents and make the hot queries fast: compound + multikey (array/nested-field) indexes the planner actually uses (IXSCAN, not COLLSCAN)
- [ ] 06-mongodb-vs-jsonb — same containment query, nested-field match, and partial update on MongoDB vs Postgres JSONB+GIN, each properly indexed, for an honest head-to-head
- [ ] 07-nosql-decision-writeup — written: per-workload memo on which of the six patterns earn a dedicated store, which are just Postgres-able coordination, grounded in what you built and measured
- [ ] 08-capstone (capstone)
  - [ ] CP1: steady materialization — full category-enriched event stream drained by a two-consumer group converges t08_state (count, price_sum, per-category count) to ground-truth current_state on a clean run
  - [ ] CP2: chaos convergence — at-least-once + watermarked idempotent materialize survives a mid-batch crash (entries stuck in the PEL): XAUTOCLAIM reclaim + forward drain still hit ground truth exactly with XPENDING 0
  - [ ] CP3: design memo — DESIGN.md defended (control-plane, watermark idempotency, crash recovery, rate shaping, failure modes), CP1+CP2 still green

## 11-python-concurrency

- [ ] 01-event-loop-and-blocking — rescue a fetcher that looks async but is serial and runs a blocking call inline on the loop: fetch every path concurrently AND offload the blocking (GIL-releasing) parse off the event-loop thread so a heartbeat coroutine keeps ticking
- [ ] 02-taskgroup-structured-concurrency — replace `create_task` + `gather` (leaks siblings on first failure, silently swallows a second one) with `asyncio.TaskGroup`: first failure cancels every sibling, results come back in input order, nothing left alive
- [ ] 03-cancellation-and-timeouts — a `guarded_operation` that times out without leaking: the timeout releases the resource-pool slot, external cancellation propagates as cancellation (not swallowed), and a shielded finalizer still runs to completion
- [ ] 04-backpressure-bounded-queue — a bounded `asyncio.Queue` producer/consumer where a slow consumer forces the producer to wait, so peak traced memory tracks `max_in_flight`, not `produce_n` (validator asserts the peak stays flat as `produce_n` 4x's; an unbounded buffer grows ~4x)
- [ ] 05-semaphore-rate-limiting — bounded concurrency plus a rate cap against the mock peer, never tripping the peer's concurrency/rate gates, no leaked tasks
- [ ] 06-gil-decision-matrix — implement one CPU-bound and one I/O-bound workload three ways (sequential / ThreadPoolExecutor / ProcessPoolExecutor, plus asyncio for I/O), benchmark on your own hardware via `baseline.py`, and defend a decision matrix; validator asserts only the robust relative truths from your measured numbers (processes beat threads for CPU work — the GIL; concurrency wins big for I/O)
- [ ] 07-sync-async-bridging — two bridging bugs: offload a blocking call off the loop with a bounded `to_thread`/`run_in_executor` while preserving input order, and drive the async entrypoint from plain synchronous code via `asyncio.run`
- [ ] 08-profiling-py-spy — profile a LIVE async worker with py-spy (`record` / `dump --pid`) to find a hidden CPU-bound function blocking the loop, name it, and fix it so the event loop stays responsive under load
- [ ] 09-capstone-async-scraper (capstone)
  - [ ] CP1: steady state — scrape every corpus page under a hard concurrency cap with backpressure; the aggregate (count, price_sum, per-category count) matches committed ground truth exactly, the cap is held, no tasks leak
  - [ ] CP2: chaos — with injected 500s and latency jitter, retry + per-request timeout without leaking tasks or connections and still converge to the identical ground-truth aggregate
  - [ ] CP3: design memo — DESIGN.md defended (bounded concurrency, backpressure, cancellation/timeouts, retry, failure modes), CP1+CP2 still green

## 12-api-engineering

- [ ] (tasks are added when the module is generated)

## 13-scraping-at-scale

- [ ] (tasks are added when the module is generated)

## 14-stats-and-ml-foundations

- [ ] (tasks are added when the module is generated)

## 15-llm-in-pipelines

- [ ] (tasks are added when the module is generated)

## 16-testing-engineering

- [ ] (tasks are added when the module is generated)

## 17-system-design

- [ ] (tasks are added when the module is generated)

## 18-rust-track

- [ ] (tasks are added when the module is generated)

## 19-ts-track

- [ ] (tasks are added when the module is generated)

## 20-kubernetes

- [ ] (tasks are added when the module is generated)

## ci-meta

- [ ] (tasks are added when the module is generated)
