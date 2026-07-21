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

- [ ] 01-pagination-offset-vs-cursor — build `LIMIT/OFFSET` and keyset cursor pagination over 200k `shop.products`, then benchmark on your own machine: deep-offset latency degrades materially with depth while cursor latency stays flat, and a full cursor sweep returns every product exactly once (count + id checksum both match)
- [ ] 02-response-caching-redis — cache-aside a category summary aggregation in Redis (TTL + explicit invalidation route), with `X-Cache: HIT/MISS` and a byte-for-byte identical cached body, proven both correct against an independent Postgres oracle and materially faster on a relative baseline
- [ ] 03-rate-limiting-and-quotas — an atomic single-round-trip (Lua `EVAL`) per-key rate limit plus a longer-window quota guarding `/search`, admitting exactly `RATE_LIMIT` requests under a genuinely concurrent burst (not just sequentially) and returning 429 + `Retry-After` distinguishing rate-limited from quota-exceeded
- [ ] 04-background-jobs-and-idempotency — an "export order history" endpoint that enqueues and returns 202 immediately, where repeat or 20-concurrent requests sharing one `Idempotency-Key` all resolve to the SAME job via an atomic `INSERT ... ON CONFLICT`, never a check-then-insert race
- [ ] 05-streaming-large-exports — an NDJSON `/export/products` that streams via a bounded batch/server-side cursor at every layer (Postgres → generator → response), so peak traced memory barely moves between a small and the full 200k-row export instead of scaling with row count
- [ ] 06-sql-injection — exploit a real string-interpolated `/search` endpoint (leaking `shop.users` via UNION-based injection), then close it two layers deep: bound parameters plus a least-privilege `t06_search` Postgres role with zero access to `shop.users`
- [ ] 07-auth-jwt-and-refresh — RS256 login/refresh/`/me` that survives a forged-token trap battery (`alg: none`, RS256/HS256 confusion, tampered/expired tokens, access/refresh type confusion, cross-user probes) plus refresh-token rotation where a replayed already-used token revokes the entire token chain, not just itself
- [ ] 08-secrets-management — a scanner that finds every planted secret in both a repo's working tree and its full git history (with zero false positives on realistic decoys), plus converting a compose file's plaintext `PG_PASSWORD` to the docker `secrets:`/`*_FILE` convention with a loader that fails loudly instead of falling back to plaintext
- [ ] 09-load-test-and-bottleneck-hunt — given a shipped, correct `/catalog/{category_id}` endpoint with no hints, diagnose why it falls over under concurrency (N+1 queries, blocking calls on the event loop, pool sizing — measure/hypothesize/fix/re-measure) and raise RPS/p95 on a relative baseline without changing a single byte of its response
- [ ] 10-capstone-catalog-api (capstone)
  - [ ] CP1: steady state — cursor pagination, cache-aside category summary, atomic rate limiter, and JWT auth combined into one service: a full unfiltered pagination sweep matches the committed ground truth exactly (count 200000 + id checksum), cache HIT/MISS agree with an independent oracle, a concurrent burst admits exactly `RATE_LIMIT`, and every protected route rejects unauthenticated calls then accepts a real token
  - [ ] CP2: chaos/hardening — the same service survives a SQLi battery against `/catalog/search` (never leaks `shop.users`, never 500s), forged/expired/rotated-and-replayed tokens all rejected, the rate limiter holds under a heavier multi-key concurrent burst, concurrent readers never see a torn cache value, and a Redis-down instance still answers the summary endpoint with `X-Cache: BYPASS` instead of 500 — while CP1's exact ground-truth sweep still passes
  - [ ] CP3: design memo — `DESIGN.md`'s six sections (pagination at scale, cache correctness, rate-limit atomicity, JWT rotation, SQLi defense, Redis as optional dependency) filled in with real content, then CP1 and CP2 re-run as subprocesses and both still green

## 13-scraping-at-scale

- [ ] 01-hostile-target-recon — probe the target from the outside (no peeking at `target-spec.json`) to discover the header gate, the token-bucket rate limit's rough shape, and where honeypot traps hide in listing HTML, then write a client that crawls the full real-product catalog with zero bans and zero honeypot hits (validator checks the discovered id set is exactly the real product ids, `banned=False`, `honeypot_hits=0`, and a record sample matches the catalog oracle including the JS-only `rating`/`shipping_info`)
- [ ] 02-data-quality-contracts — a pandera schema over scraped product records that catches every planted defect (missing/`N/A`/negative price, empty title, bad currency, truncated description) and routes clean vs. quarantined records to separate file sinks, where the quarantine sink is EXACTLY ground truth's bad-record id union across all 6 defect types and the clean sink is exactly its complement — no defect silently passes through as "clean"
- [ ] 03-change-detection-and-fingerprinting — a day-over-day fingerprint that flags every product whose price or stock actually changed while stripping the target's volatile per-request nonce, validated against the true changed-id set per day plus a negative control (a known-unchanged page must not be flagged across two days, even as its nonce and markup version vary)
- [ ] 04-markup-resilience — a selector/extraction layer with real per-field fallback chains that correctly extracts every field across all 4 markup versions the SAME crawl serves (plain divs, schema.org microdata, JSON-LD-only pricing, a JS-data-island shell), holding 1.0 completeness per forced version with no version special-cased away
- [ ] 05-scraping-economics-budget-router — a cost model per 1M pages (plain HTTP vs. headless-render vs. mixed) plus a budget router that decides per product whether the cheap HTML fetch suffices or the 8x-more-expensive render step is actually needed, meeting the `0.98` completeness target at modeled cost near the mixed-strategy reference (well under all-render) — completeness alone is gameable by "always render," so the validator gates on both
- [ ] 06-observability-prometheus-grafana — instrument your own scraper with Prometheus metrics (requests, 429s/403s, bans, honeypot hits, queue depth, latency histogram) exposed on `:9113/metrics` and scraped by the `prometheus` container, plus a Grafana dashboard JSON; the must-pass check is your `/metrics` content (families/labels/histogram move under a paced two-client crawl), Prometheus/Grafana live checks are skip-if-down
- [ ] 07-capstone-data-quality-platform (capstone)
  - [ ] CP1: steady state (day 0) — one `run_pipeline` combining polite crawling (task 01), 4-version-resilient extraction (04), pandera clean/quarantine gating (02), the budget router (05), and metrics instrumentation (06); discovered ids exactly the real set with zero honeypots/bans, quarantine == ground-truth bad-record union and clean == complement (each row re-checked), a cross-version clean sample matches the catalog oracle, completeness meets `0.98` at modeled cost near the mixed reference, and the metrics registry shows real movement across every required family
  - [ ] CP2: chaos + change detection — the same pipeline run with `chaos=True` for days 0 and 1 (markup version cycles by wall-clock, not product id), where extraction completeness stays above threshold on both runs with no bans, `changed_between(0, 1, ...)` returns EXACTLY the oracle changed subset (with a proven negative control), and a second identical call (interrupted-then-resumed) converges to the same exact result — no drift, no duplicates
  - [ ] CP3: design memo — `DESIGN.md`'s seven sections (architecture/data flow, defense handling, data-quality contract, change-detection design, cost/budget tradeoffs, observability, scaling to 10x) filled with grounded content, then CP1 and CP2 re-run as subprocesses and both still green
- [ ] k8s-bonus (optional) — grow the scraping infrastructure into a from-scratch `spider-platform` Helm chart (provided filled `values.yaml`; you write the templates): a resource-bounded spider Deployment with liveness+readiness probes, a matching HPA, and a PDB; validator runs `helm lint` + `helm template` and asserts the rendered manifests (a live kind/k3d deploy is the optional stretch)

## 14-stats-and-ml-foundations

- [ ] 01-vectorization-and-broadcasting — rewrite a colleague's row-by-row Python loops (per-category z-score, rolling mean, per-group min-max) as vectorized numpy/broadcasting; validator checks correctness against the provided naive baseline and asserts a machine-relative per-function speedup (`baseline.py` writes a gitignored `baseline-local.json`)
- [ ] 02-eda-scraped-prices — first-pass EDA of the scraped dataset computed BOTH in pandas and polars and proven to agree (the polars-vs-pandas taste) plus an EDA figure; validator grades facts (counts, missingness, valid-price median/mean, busiest day) against ground truth / an independent recompute
- [ ] 03-matplotlib-fundamentals — a 4-panel dashboard (log-scale price histogram, price-by-category boxplot, daily-median time series, per-source-site bar) with every axis labeled; validator structurally checks 4 axes + labels + log scale via `require_figure` and grades a facts dict
- [ ] 04-price-distributions-not-normal — quantify that scraped prices are heavily right-skewed (skew/kurtosis, normaltest) and show a log transform normalizes them, with histograms/Q-Q plots; validator recomputes the scipy stats independently and asserts log-is-more-normal
- [ ] 05-outliers-vs-parsing-errors — separate planted price PARSING ERRORS (negative/zero/NaN/missing-decimal x100) from GENUINE OUTLIERS (the real expensive tail) using robust stats + a whole-dollar/divide-by-100 signature; validator grades per-kind recall with a ZERO genuine-outlier-false-positive gate (a naive 3-sigma rule fails it)
- [ ] 06-confidence-intervals — Student t confidence interval for a mean price from a fixed 200-page sample plus the 1/sqrt(n) width law; validator reproduces the pinned sample, recomputes the reference CI via scipy, and checks population-mean containment and the width ratio
- [ ] 07-bootstrap — percentile bootstrap CI for the MEDIAN price (where no analytic SE exists), with a pinned resampling recipe; validator reproduces the reference bootstrap CI and checks it brackets the population median
- [ ] 08-ab-test-scraping-strategies — a pooled two-proportion z-test comparing two scraping strategies' extraction success (p-value, effect size, decision) over a fixed fixture; validator recomputes the test via scipy and confirms the significant branch fires
- [ ] 09-correlation-vs-causation — expose the discount/units_sold correlation (~0.79) as a category-confounded Simpson's-paradox artifact: pooled vs within-category correlations, identify the confounder, a colored scatter, and an `ANSWER.md` writeup; validator grades the correlations + confounder + gated writeup
- [ ] 10-sklearn-pipeline-leakage — reproduce an inflated held-out R^2 from a target-encoded (`product_id`) feature computed over all rows, then measure the honest R^2 with the encoding fit on train only inside a proper sklearn Pipeline; validator asserts the leak gap and a minimum honest R^2 on the fixed split
- [ ] 11-feature-engineering — beat a deliberately weak baseline (R^2 ~ 0) by engineering features from raw scraped fields (category/site one-hot, calendar parts, title text / TF-IDF) to predict log price; validator asserts an R^2 gain and minimum over the fixed split
- [ ] 12-pytorch-tensors-autograd — torch tensors + autograd on toy examples: gradient-check autograd against finite differences and analytic gradients, then fit a linear regressor by manual gradient descent and confirm convergence to the closed-form OLS solution, with a loss-curve plot
- [ ] 13-capstone-text-classifier (capstone) — predict product category from the scraped title
  - [ ] CP1: classical baseline — TF-IDF / bag-of-words + a linear classifier on the fixed stratified split reaching macro-F1 >= threshold on held-out
  - [ ] CP2: PyTorch classifier — an embedding / bag-of-words torch model on the same split reaching a higher macro-F1 threshold on held-out
  - [ ] CP3: design memo — `DESIGN.md` (data/labels, text representation, architecture, training/eval, per-class error analysis, scaling) filled, then CP1 and CP2 re-run as subprocesses and both still green

## 15-llm-in-pipelines

- [ ] 01-swappable-llm-client — a pipeline-grade resilience wrapper over `harness.llm`: enforced structured/JSON output with schema validation + bounded reask on invalid output, timeout + bounded retry-with-backoff on transient errors, primary→fallback provider swap on repeated failure, and token/latency accounting; tested with injected fake providers (flaky/returns-junk-then-valid) for the deterministic retry/reask/fallback paths plus one live smoke call against real Ollama
- [ ] 02-structured-extraction — extract `{name, brand, price, currency, in_stock}` from selector-hostile HTML snippets (prose pricing, attribute-only fields, entity/whitespace noise, malformed tags, cents-only pricing); graded field-level precision/recall/exact-match vs. gold with 7B-realistic thresholds
- [ ] 03-classification-and-enrichment — classify + enrich records whose title/description signal is deliberately diluted (generic-brand pool, cross-category noun/description noise); accuracy/macro-F1 thresholds, a constant-prediction baseline must fail
- [ ] 04-embedding-dedup — dedup same-product-different-title listings via `nomic-embed-text` + cosine threshold/clustering; pairwise-F1 threshold, both all-singleton and all-one-cluster degenerate baselines must fail
- [ ] 05-mini-rag — chunk + embed a small synthetic "Sandbox Handbook" corpus, retrieve top-k, answer with citation; retrieval hit@k as the robust primary metric, answer-contains-fact as a secondary metric
- [ ] 06-capstone (capstone) — end-to-end enrichment pipeline (extract → classify/enrich → embed-dedup → clean catalog) with a quality/confidence gate routing low-confidence records to quarantine, plus a RAG "explain this product" step
  - [ ] CP1: steady state — clean inputs, hit quality/confidence thresholds vs. gold across the full pipeline
  - [ ] CP2: chaos — messier inputs, injected malformed model outputs, forced provider fallback; must degrade gracefully, quarantine correctly, and still converge
  - [ ] CP3: design memo — `DESIGN.md` filled, then CP1 and CP2 re-run as subprocesses and both still green

## 16-testing-engineering

The inversion: the sandbox ships a GIVEN correct `src/impl.py`; you write the TEST SUITE. Grading is mutant-killing — your suite must pass against the correct impl AND fail against every seeded mutant (a hidden bank under `.authoring/mutants/`). `.authoring/` is off-limits until you finish. Tasks 03/04/07 need Docker (testcontainers).

- [ ] 01-property-based-parsing — Hypothesis property tests for a given price/currency parser (`parse_price`/`format_price`): round-trip, idempotence, output-range, and error-typing invariants; must kill 6 mutants (dropped currency, separator confusion, sign/abs bug, silent-None-instead-of-raise, cents truncation, currency-case)
- [ ] 02-stateful-and-metamorphic — a `RuleBasedStateMachine` + metamorphic relations against a given LRU-cache-with-TTL (injected deterministic clock, no sleeps); must kill 6 mutants (FIFO-not-LRU, TTL off-by-one, capacity off-by-one, get/re-put recency bugs, expired-counted-in-len)
- [ ] 03-integration-postgres-testcontainers — integration tests against a real ephemeral `postgres:16` for a given `PriceRepo` (idempotent upsert, watermark incremental load, keyset pagination); must kill 7 mutants (wrong ON CONFLICT, DO NOTHING, missing commit, cursor off-by-one, watermark >/>=, dropped id tiebreak, limit off-by-one)
- [ ] 04-integration-redis-testcontainers — integration tests against a real ephemeral `redis:7` for a given atomic `RateLimiter` + `DedupFilter`; must kill 7 mutants (TTL never set, non-atomic check-then-set, dropped namespace, boundary off-by-one, EXPIRE-every-call, dedup missing NX, dedup missing EX)
- [ ] 05-contract-tests-api — consumer contract tests (httpx + jsonschema) against a given module-12-style FastAPI catalog; must kill 8 mutants (field rename, wrong error status, next_cursor edge polarity, id/price type drift, error-envelope shape, dropped cache header)
- [ ] 06-mutation-testing-taste — the reflexive one: run a real mutation tool (cosmic-ray) on a given module + a given weak-but-green suite, read the survivors, and strengthen the tests until the survivor count reaches zero (graded by the tool, not the custom harness)
- [ ] 07-capstone-scrape-to-serve-test-suite (capstone) — a layered suite for a given one-file scrape->serve stack (parser + Postgres repo + Redis cache + FastAPI)
  - [ ] CP1: unit + property layer — kills the pure-parser mutant subset, no containers
  - [ ] CP2: integration + contract layer — testcontainers Postgres+Redis + ASGI/jsonschema; kills the stateful DB/cache/API mutant subset
  - [ ] CP3: test-strategy memo — `DESIGN.md` (testing pyramid, what each layer catches, where mutation testing found gaps, extending to CI) filled, then CP1 and CP2 re-run as subprocesses and both still green

## 17-system-design

The writing module, and it runs ongoing alongside the others. Each task is graded on two gates: a `DESIGN.md` checked structurally (required sections, no leftover placeholders, grounding vocabulary, quantitative claims, hostile-review questions actually answered) and a back-of-the-envelope capacity model in `src/estimate.py` checked numerically against the validator's own independent recomputation across several perturbed workloads — so hardcoded constants fail. No Docker, no ports.

- [ ] 01-price-monitoring-10k-sites — crawl architecture and freshness tiers for ~10k sites; capacity model sizes the worker fleet (Little's law at peak) and the proxy budget
- [ ] 02-price-history-storage — five years of price history serving both a per-product range read and a per-category analytical read; layout, ordering key, change-only storage, hot/cold tiering, storage cost
- [ ] 03-delivery-with-client-slas — per-client feed delivery under contractual SLAs; error budgets, prioritization under a shared crawl budget, backfill drain after an outage, money at risk
- [ ] 04-multi-tenant-platform — opening the platform to paying tenants on shared infrastructure; isolation boundaries, admission control, weighted max-min fair share, noisy-neighbour containment, cost attribution
- [ ] 05-outage-postmortem-redesign — inverted: a given `INCIDENT.md` with evidence but no analysis; reconstruct the causal chain, quantify retry amplification and pool exhaustion, then redesign for blast-radius containment
- [ ] 06-capstone-design-review (capstone) — the whole price-intelligence platform as a staff-level design-review packet
  - [ ] CP1: requirements and capacity — scope, SLIs/SLOs, workload characterization, capacity and cost models (the numeric gate)
  - [ ] CP2: architecture, data flow and failure — components, contracts, storage/serving layout, multi-tenancy, failure modes, degradation ladder, 10x, plus three ADRs with rejected alternatives argued
  - [ ] CP3: defence — twelve hostile-review questions answered, a risk register, a `REVIEW.md` self-critique, then CP1 and CP2 re-run as subprocesses and both still green

## 18-rust-track

- [ ] (tasks are added when the module is generated)

## 19-ts-track

- [ ] (tasks are added when the module is generated)

## 20-kubernetes

- [ ] (tasks are added when the module is generated)

## ci-meta

- [ ] (tasks are added when the module is generated)
