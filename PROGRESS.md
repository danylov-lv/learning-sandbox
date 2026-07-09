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

- [ ] (tasks are added when the module is generated)

## 07-streaming

- [ ] (tasks are added when the module is generated)

## 08-cdc-debezium

- [ ] (tasks are added when the module is generated)

## 09-olap-clickhouse-duckdb

- [ ] (tasks are added when the module is generated)

## 10-nosql-patterns

- [ ] (tasks are added when the module is generated)

## 11-python-concurrency

- [ ] (tasks are added when the module is generated)

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
