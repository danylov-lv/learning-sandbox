# learning-sandbox

A project-based learning sandbox for closing one specific gap: the data layer (SQL optimization, storage, modeling, streaming semantics) for an engineer who already ships production Python (Scrapy, asyncio), runs RabbitMQ and Kubernetes daily, and writes Helm charts.

## What this is

Every module is a set of mini-projects, each with:

- a realistic backstory (you inherited a system, you're on call, a migration went sideways),
- seeded, deterministic data generation at a chosen scale,
- automated, objective tests/validators,
- tiered hints (`hint-1.md` direction, `hint-2.md` more specific, `hint-3.md` concrete approach).

There are **no reference solutions anywhere in this repository**. Only hints and tests. You write all the code yourself; the tests and validators tell you whether it's correct (and, where relevant, whether it's fast enough).

## How to work with it

- Budget roughly one evening per week per task. Most tasks are 1–2 evenings; capstones span 2–4 evenings.
- Every module is self-contained: its own `docker-compose.yml` spins up whatever services it needs (Postgres, MinIO, Kafka/redpanda, ClickHouse, ...). Nothing is installed globally.
- Python tooling is per-module via `uv`: `uv sync` to install, `uv run` to execute scripts/tests. Each module has its own `pyproject.toml` and committed `uv.lock`.
- Fill in that task's `NOTES.md` after finishing it — what you tried, what broke, what you'd do differently. This is your own record, not graded by anything.

## Recommended order + estimated effort

| Order | Module | One-liner | Est. evenings |
|---|---|---|---|
| 1 | 01-sql-foundations | Warm-up: joins, window functions, CTEs, time-bucketed aggregations on 3–5M rows | 3–4 |
| 2 | 02-sql-optimization | **PRIORITY**: inherited wrecked marketplace DB — EXPLAIN, indexing, partitioning, bloat, locking, N+1; capstone audit | 8–10 |
| 3 | 03-data-modeling | Design a price-tracking platform schema: normalization, SCD2, temporal history, star schema | 4–5 |
| 4 | 04-storage-and-formats | Parquet vs CSV/JSON, pyarrow, predicate pushdown, partitioned datasets, Delta Lake, MinIO | 4–5 |
| 5 | 05-distributed-processing-spark | PySpark DataFrame API, shuffles/skew, broadcast joins, Spark UI, polars calibration task | 6 |
| 6 | 06-pipelines-and-orchestration | Airflow ETL with idempotency/backfill, dbt, Prefect comparison, pandera data contracts | 6–7 |
| 7 | 07-streaming | Kafka (redpanda) for an RMQ practitioner: log vs queue, offsets, exactly-once, compacted topics | 5–6 |
| 8 | 08-cdc-debezium | Postgres → Debezium → Kafka → downstream mart; schema evolution, convergence validation | 4–5 |
| 9 | 09-olap-clickhouse-duckdb | MergeTree, materialized views, Postgres-vs-ClickHouse at 50M rows, DuckDB on Parquet | 4–5 |
| 10 | 10-nosql-patterns | Redis beyond cache (rate limiter, locks, dedup, streams), MongoDB vs Postgres JSONB | 5–6 |
| 11 | 11-python-concurrency | Event-loop internals, broken-code rescues, cancellation, backpressure, GIL benchmarks, py-spy | 5–6 |
| 12 | 12-api-engineering | Own FastAPI stack: cursor pagination, Redis caching, rate limiting, background jobs, streaming exports, plus a security block (SQLi, JWT auth, secrets) and a load-test bottleneck hunt | 6–7 |
| 13 | 13-scraping-at-scale | Hostile local target site; data-quality platform, change detection, selector resilience, cost model, Prometheus/Grafana | 7–8 |
| 14 | 14-stats-and-ml-foundations | numpy/pandas/viz, applied stats on scraped prices, sklearn + PyTorch taste | 6–7 |
| 15 | 15-llm-in-pipelines | Local Ollama 7B: structured extraction, enrichment, embedding dedup, mini-RAG | 4–5 |
| 16 | 16-testing-engineering | Inverted: you write the tests against a given impl, graded by mutant-killing — Hypothesis property/stateful tests, testcontainers (Postgres/Redis), contract tests, cosmic-ray mutation testing | 5–6 |
| 17 | 17-system-design | Six written design exercises (crawl capacity, price-history storage, SLA delivery, multi-tenancy, an outage postmortem, capstone design review) graded on two gates: a structurally checked design doc plus a numerically checked capacity model; hostile-interviewer questions to defend against (ongoing, alongside other modules) | 6–7 |
| any | 18-rust-track | 7–8 projects: CSV→Parquet converter, URL health checker, TUI dashboard, bitcask KV store, toy interpreter | independent pace |
| any | 19-ts-track | Advanced type system: type-challenges progression, zod-validated SDK for a module-12-shaped API, contract-first monorepo capstone | 6–9 |
| any | 20-kubernetes | Manifests from zero → own Helm charts → ops/debugging → networking/state → Argo CD internals → optional operator on kopf; kind/k3d local cluster | 12–15 |
| — | ci-meta | GitHub Actions CI for the sandbox itself: changed-module detection + service containers | 1 |

Suggested path: 01 first (warm-up), then 02 immediately — it's the priority module for closing the gap — then 03, 04. After that, 05–10 form the data-engineering core and are best done in order (each reuses infrastructure from the previous ones). 11–16 can follow in order. 17 (system design) runs ongoing alongside everything else. 18 (Rust), 19 (TypeScript), and 20 (Kubernetes) are independent tracks you can pick up anytime, at your own pace.

## Verification philosophy

- Checks are objective: pytest suites, validator scripts, or measurable metrics — never "does this look right to you."
- Structural checks are preferred over timing checks wherever possible: e.g. "the EXPLAIN plan must not contain `Seq Scan` on this table," or "the aggregate result must match the reference computation," rather than "this must run in under N ms."
- Where timing genuinely matters (query optimization, streaming throughput), a baseline script benchmarks the task on *your* machine first and later checks are expressed relative to that local baseline, not an absolute number.

## k8s bonus levels

Modules **06**, **07**, and **13** (and optionally **05**) include an optional `k8s-bonus/` level: deploy that module's project to a local `kind`/`k3d` cluster using your own Helm chart, with HPA, PodDisruptionBudgets, and resource limits derived from what you actually measured earlier in the module.

Module **20-kubernetes** is the real k8s track — the bonus levels above stay as light exercises. Recommendation: complete module 20's Arc 1–2 (raw manifests, your own Helm chart) before attempting the k8s-bonus levels of 06/07/13.

## Toolkit track

A separate family of small, tool-fluency modules (3–6 single-evening tasks each, no capstones) about using tools well, as opposed to the main modules' engineering topics. **Dip in anytime, no prescribed order** — with one exception: do **t1's task 01** (project memory) early, since a good `CLAUDE.md` improves every other task in the repo. These modules are non-Docker and use no host ports; each still ships its own `pyproject.toml` + `uv.lock` and objective validators.

| Module | One-liner | Est. evenings |
|---|---|---|
| t1-ai-assisted-engineering | Advanced Claude Code practice: project memory, custom subagents, hooks/guardrails, headless `claude -p` + CI, a hand-built MCP server, and reviewing plausible-but-flawed AI patches | 3–4 |
| t2-modern-python-toolchain | uv (project + tool management), ruff (lint + format), `mypy --strict`, pre-commit wiring, packaging an internal library with a src layout — every check runs the real tool | 2–3 |
| t3-cli-data-toolkit | Explore/fix data from the terminal: jq on nested JSON, ripgrep/fd fluency, the DuckDB CLI over Parquet/CSV, honest hyperfine micro-benchmarks, GNU parallel batch processing | 2–3 |
| t4-git-advanced | Beyond add/commit/push: interactive rebase cleanup, `git bisect` regression hunt, worktrees for parallel work, reflog rescue, and a commit-history policy writeup | 2–3 |

## Planned modules (second wave)

Not yet scheduled, one-liners only:

- **Network layer for scraping** — TLS fingerprinting (JA3), how anti-bot systems see clients, HTTP/1.1 vs HTTP/2 semantics, connection pooling internals, DNS, traffic analysis with mitmproxy.
- **Deep AI track** (after 14–15) — fine-tuning small models for extraction, building evals, local serving and inference optimization.
- **IaC / Terraform** — infrastructure as code, if/when work moves cloudward.
