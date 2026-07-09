# Global spec — read this once per session

## Profile & hardware (calibrate ALL difficulty to this)

Build a learning sandbox repository `learning-sandbox` for project-based engineering skill development. Calibrate task difficulty to my profile — do NOT dumb it down:

- 2 years of commercial web scraping: 1 year requests/bs4, 1 year Scrapy
- Daily work with distributed architecture: producer/consumer spiders communicating via RabbitMQ, deployed to Kubernetes via existing Helm charts and an Argo template (I fill templates, I don't design charts — see module 20 spec)
- Backend background: Django, FastAPI; NestJS project at work
- Large personal project: NestJS API + workers + scheduler + Next.js web + third-party API integrations
- Main acknowledged gap: SQL optimization. Overall goal: growth to the systems level — storage, scaling, data architecture

Meaning: queues, workers, containers, k8s are my daily context. Tasks like "learn what a queue is" or "write your first spider" are useless to me. Weak areas: the data layer (SQL, storage, formats, modeling) and streaming semantics. Strong areas: delivery, process orchestration, infrastructure.

Hardware: Windows machine, 32 GB RAM, RTX 3070 Ti Super 8 GB VRAM, Docker available. I work both inside Docker and natively on Windows. Postgres always in Docker.

## Orchestration rule (critical, follow strictly)

You (the main model) act ONLY as orchestrator and architect: design the structure, decompose the work, write task specs for subagents, review their output, assemble the result. ALL content generation (task texts, seed scripts, datasets, tests, configs, boilerplate) must be delegated to subagents on cheaper models (Haiku / Sonnet) via the Task tool. Do not write files yourself except for final review fixes where a subagent failed. Run subagents in parallel wherever tasks within the current module are independent (e.g., several tasks of one module generated simultaneously). If a subagent produces garbage — give it specific feedback and regenerate; do not redo the work yourself.

## Sandbox philosophy

- **Project-based**: not syntax drills but mini-projects with a realistic backstory, input data, and completion criteria. Every project is a story ("you inherited a marketplace DB where query latency degraded"), not an abstraction.
- **I write all code myself.** The sandbox provides: problem statement, data, environment, auto-tests for self-checking, and tiered hints. **NO reference solutions anywhere** — only hints and tests. `hints/hint-1.md` (direction), `hint-2.md` (more specific), `hint-3.md` (concrete approach, still no ready code).
- **Verifiability**: every task must have an objective self-check — pytest/cargo test/jest, a validator script, or a measurable metric. Since timing thresholds vary by machine: prefer structural checks ("EXPLAIN must not contain Seq Scan on orders", "result matches reference aggregate") as primary, and where timing matters, include a `baseline.py` that benchmarks MY machine first and sets relative thresholds (e.g., "optimized query ≥ 20x faster than the naive one").
- **Task sizing — two formats, mixed**: (a) single-evening tasks (2–3 hours), (b) multi-day block projects (a module capstone spanning 2–4 evenings, split into checkpoints with intermediate tests, in the spirit of "100 days of X" day-blocks). Every module ends with a capstone.
- Environments via `docker-compose` per module: spin up and work. Nothing installed globally.
- **All materials in English** — READMEs, task texts, hints, comments.

## Repository structure

```
learning-sandbox/
├── README.md               # learning map, order, how to work with the sandbox
├── PROGRESS.md             # flat checklist of all tasks
├── GENERATION_STATE.md     # batch generation state
├── 01-sql-foundations/
├── 02-sql-optimization/    # PRIORITY #1 — my main gap
├── 03-data-modeling/
├── 04-storage-and-formats/
├── 05-distributed-processing-spark/
├── 06-pipelines-and-orchestration/
├── 07-streaming/
├── 08-cdc-debezium/
├── 09-olap-clickhouse-duckdb/
├── 10-nosql-patterns/
├── 11-python-concurrency/
├── 12-api-engineering/
├── 13-scraping-at-scale/
├── 14-stats-and-ml-foundations/
├── 15-llm-in-pipelines/
├── 16-testing-engineering/
├── 17-system-design/
├── 18-rust-track/
├── 19-ts-track/
├── 20-kubernetes/
├── toolkit/
│   ├── t1-ai-assisted-engineering/
│   ├── t2-modern-python-toolchain/
│   ├── t3-cli-data-toolkit/
│   └── t4-git-advanced/
└── ci-meta/                # meta-task: CI for the sandbox itself
```

## Task format

```
NN-task-name/
├── README.md        # backstory, what's given, what's required, completion criteria, topics to read up on (topics, not links)
├── docker-compose.yml or module-level environment
├── data/ or seed/   # data or generation script
├── src/             # scaffold with TODOs where appropriate (minimal boilerplate — I write the code)
├── tests/           # auto-verification
├── hints/           # hint-1..3
└── NOTES.md         # template: "What I learned / Gotchas / Open questions" — I fill it after completion and copy to my knowledge vault
```

## Quality requirements

- Generate data via scripts (faker/numpy with fixed seeds), realistic distributions; never commit gigabytes to git — generators only.
- Every docker-compose must actually start; subagents must verify by running, not by eyeballing.
- Root README: recommended order (02 right after warm-up 01), estimated time per module, the rule "one evening per week — one or two tasks, capstones span multiple evenings".
- PROGRESS.md — flat checklist of all tasks with day-block groupings for capstones.
- Since k8s/Helm is my daily tool, add an optional `k8s-bonus/` level to modules 06, 07, and 13 (plus a spark-on-k8s taste in module 05 if trivial to include): deploy that module's project to a local cluster (kind/k3d) with your own Helm chart — HPA for consumers, PDB, resource limits based on measurements.
- Meta-task `ci-meta/`: a GitHub Actions workflow that, on push, detects the changed module and runs its tests (service containers for Postgres/Redis/etc.). One evening; doubles as CI practice and a living progress check.
- All generated materials in English.

## Second wave roadmap (out of scope — do NOT generate now)

List the following in the root README under "Planned modules (second wave)" as one-liners, so future sessions can generate them via GENERATION_STATE.md in the same style. Do not create their directories or tasks today:

- **Network layer for scraping**: TLS fingerprinting (JA3) and how anti-bots see clients, HTTP/1.1 vs HTTP/2 semantics, connection pooling/keep-alive internals, DNS, traffic analysis with mitmproxy.
- **Deep AI track** (continuation of modules 14–15, after the base is done): fine-tuning small models for extraction tasks, building evals, local serving and inference optimization.
- **IaC / Terraform**: infrastructure as code, if/when work moves cloudward.

## Generation process (replaces any batch plan)

- Work module-by-module in the order of `GENERATION_STATE.md`, ONE module at a time.
- For each module: read ONLY its section from `SPEC.md` (delimited by `## MODULE:` headings — locate via grep and read that range only, never the whole file), decompose it for subagents, generate, verify (docker-compose must start, tests must run), mark it done in `GENERATION_STATE.md`, then proceed to the next.
- Context hygiene: subagents write files directly to disk and return only short summaries — never their full output — to the orchestrator. The orchestrator must not read generated task content back into context except spot-checks.
- When the session's limit approaches: finish the current module cleanly, update `GENERATION_STATE.md`, stop. A fresh session resumes from the state file + this global spec alone.

---

# Module specs

## MODULE: Module 01-sql-foundations

**SQL foundations (short, warm-up).** PostgreSQL in Docker, seeded with 2–3 related tables at 1–5M rows (generated by script, realistic distributions — not uniform). 8–10 tasks: complex joins, window functions, CTEs, time-bucketed aggregations. Verification — result comparison against a reference aggregate via validator script.

## MODULE: Module 02-sql-optimization

**SQL optimization (the largest module, go deep).** Backstory: you inherit a "wrecked" marketplace DB — 10M+ rows, wrong indexes, bloated tables, slow "production" queries. 12–15 tasks progressing through: reading EXPLAIN ANALYZE, diagnosing Seq Scan / Nested Loop issues, index selection (btree, partial, covering, GIN), query rewriting, time-based partitioning, VACUUM/bloat, locking, N+1 from the application side. Each task = "here's the query, here's its current plan, here's the SLA — meet it." Verification — plan-structure checks + relative timing vs baseline. Capstone: a multi-evening "full audit" of the DB with a written optimization report template.

## MODULE: Module 03-data-modeling

**Data modeling.** Project: design a schema from scratch for a price-tracking platform with full history (close to my scraping context). Normalization vs denormalization, SCD type 2, star schema for analytics on top of OLTP. Verification — a set of business questions the schema must answer with one reasonable query each.

## MODULE: Module 04-storage-and-formats

**Storage and formats.** Parquet vs CSV vs JSON in practice: generate 5–10 GB, measure size/read speed/predicate pushdown. Tasks on pyarrow, on-disk dataset partitioning, Iceberg or Delta basics (whichever runs locally easier), object storage via MinIO in Docker. Verification — benchmark scripts with relative targets.

## MODULE: Module 05-distributed-processing-spark

**Distributed processing: Spark (core data-engineering module, recommended at work).** PySpark, local mode is enough (pip pyspark or bitnami Docker image; 32 GB RAM is plenty). Skip RDDs — DataFrame API from day one. Tasks: lazy evaluation and reading query plans (`explain()` — direct parallel to EXPLAIN from module 02), partitions/shuffles/data skew and how to see them in the Spark UI, broadcast vs sort-merge joins, why Python UDFs are slow (and pandas_udf/Arrow as the fix), window functions at 50M+ rows, reading/writing partitioned Parquet to MinIO via s3a (reuses module 04 infrastructure). One mandatory calibration task: solve the same job in polars single-node vs Spark and write down where Spark is overkill — knowing when NOT to use Spark is part of the skill. Capstone: multi-evening job that takes raw "scraped" JSON dumps → cleans, dedups, joins with reference data → writes a partitioned Parquet lake, with a shuffle-tuning pass measured in the Spark UI. Verification — result correctness validators + plan-structure checks (e.g., "the join must be broadcast, not sort-merge").

## MODULE: Module 06-pipelines-and-orchestration

**Pipelines and orchestration.** Airflow via the official docker-compose (fits in 32 GB easily). Project: ETL from raw dumps (let them be "scraped" JSONs) to a serving mart: incremental loads, idempotency, backfill, poison-record handling, failure alerting. Plus a dbt mini-project on top of the module 02 Postgres. The pipeline should orchestrate the module 05 Spark job as one of its stages. One dedicated task: migrate one DAG to Prefect and write a comparison (Prefect was a work candidate). Include 2 data-contract tasks: pandera (or Great Expectations — pick the less heavyweight) schemas as contracts at pipeline boundaries, validation gates that route violations to quarantine, and contract evolution without breaking downstream consumers. Verification — scenarios like "the middle of the pipeline died — recover without duplicates" plus "upstream added a column / changed a type — the contract catches it." Capstone: multi-evening end-to-end pipeline.

## MODULE: Module 07-streaming

**Streaming.** I work with RabbitMQ daily, so frame this module as "Kafka for someone coming from RMQ": not "what is a queue" but contrasting semantics — log vs queue, offsets vs acks, consumer groups vs competing consumers, retention and history re-reads (which RMQ lacks). Kafka via redpanda in Docker. Project: a stream of price updates → consumers aggregate into Postgres. Tasks: exactly-once on top of at-least-once (idempotency + transactional offset commits), lag monitoring, windowed aggregation, rebalancing and its consequences, compacted topics for "latest state". Final written task: "which parts of your production RMQ pipeline would benefit from Kafka, which would not, and why." Verification — consistency validator for aggregates across consumer restarts mid-stream.

## MODULE: Module 08-cdc-debezium

**CDC: Debezium.** One of the most in-demand DE topics, and conceptually it's my scraping "change detection" seen from the database side. Stack reuses modules 02 and 07: Postgres → Debezium connector → Kafka (redpanda) → consumers build a downstream mart/replica. Tasks: connector setup and snapshot vs streaming phases, handling updates/deletes downstream, schema evolution without breaking consumers, replica lag measurement and alerting, exactly-once materialization into the mart (ties into module 07 idempotency), one written task "where CDC beats periodic re-scraping/re-querying and where it's overkill". Verification — consistency validator: after a scripted burst of inserts/updates/deletes in the source, the mart must converge to the source state.

## MODULE: Module 09-olap-clickhouse-duckdb

**OLAP: ClickHouse + DuckDB.** Natural extension of my domain: analytics over scraped price history. ClickHouse in Docker. Tasks: MergeTree engines and ORDER BY as the primary index, materialized views for streaming aggregation, comparing the same analytical queries Postgres vs ClickHouse on 50M+ rows (generated), ReplacingMergeTree for dedup, TTL. Plus 2–3 DuckDB tasks: the same analytics run embedded, querying the module 04 Parquet files directly with zero servers; final written comparison "when a ClickHouse server, when DuckDB on a laptop" — knowing when the big tool is unnecessary is the point. Verification — relative benchmarks + result correctness.

## MODULE: Module 10-nosql-patterns

**NoSQL patterns.** Not a tour, but patterns: Redis beyond cache (rate limiter, distributed lock, dedup filter, stream consumer — all close to scraping needs), MongoDB schema design for semi-structured scraped documents and when it beats Postgres JSONB (and when it doesn't — comparison task included). Verification — tests over behavior (e.g., rate limiter correctness under concurrency).

## MODULE: Module 11-python-concurrency

**Python concurrency (deep, my primary language).** I already use asyncio in production tooling — target the gap between "uses async" and "understands the event loop". Tasks framed as broken-code rescues where possible ("this fetcher leaks memory and hangs — fix it"): event loop mechanics and blocking-call detection, structured concurrency with TaskGroup, cancellation and timeouts without leaks, backpressure and bounded queues, semaphores/rate limiting done right, asyncio vs threads vs multiprocessing decision matrix and where the GIL actually bites (with benchmarks), sync/async bridging (run_in_executor, to_thread), one profiling task (py-spy on a live async app). Verification — tests asserting behavior under load: no leaked tasks, bounded memory, correct throughput under injected slow peers.

## MODULE: Module 12-api-engineering

**API engineering.** FastAPI on top of the module 02 DB: pagination (offset vs cursor — with a benchmark showing why offset dies at depth), Redis caching, rate limiting, background tasks, streaming responses for large exports. Plus a security block (2–3 tasks): SQL injection hands-on — break your own module 02 DB through a deliberately vulnerable endpoint, then fix it properly (parametrization, least-privilege DB roles); authn/authz done right (JWT with refresh, common pitfalls as trap tests); secrets management (no secrets in env/compose files — docker secrets or sops, plus a "find the leaked secret in this repo" exercise). Verification — pytest + a load script (locust or a simple asyncio bombardier) with relative RPS targets; security tasks verified by exploit scripts that must fail after the fix.

## MODULE: Module 13-scraping-at-scale

**Scraping at scale (my daily domain — maximum difficulty here).** I already run distributed Scrapy via queues on k8s at work — do NOT include such tasks. Focus on everything around extraction: spin up a local "hostile" target site in Docker (JS-rendered fragments, TLS/header checks, behavioral rate limiting, unstable markup, honeypot traps). Tasks: (1) data quality layer — automated field completeness/validity monitoring on the stream (formalized as pandera contracts, reusing the module 06 approach), degradation alerting, quarantine queue for rejects; (2) change detection — incremental re-scrape of only what changed, page fingerprinting; (3) markup-change resilience — multi-level selector strategy with fallbacks and an auto-test where "the target mutates every N minutes, completeness must not drop below threshold"; (4) scraping economics — cost model per 1M pages across strategies (plain HTTP vs headless vs mixed), a "budget router" task; (5) observability — spider metrics in Prometheus + a Grafana dashboard (both in Docker). Verification — the target site breaks its markup and toggles defenses on a schedule; the system must survive and report via metrics. Capstone: multi-evening full data-quality platform around the hostile target.

## MODULE: Module 14-stats-and-ml-foundations

**Stats & ML foundations (applied, my-domain-flavored — NOT an ML-engineer track).** Purpose: a DE who understands what happens to data downstream. Three arcs. *Arc A — numpy/pandas/viz*: vectorization and broadcasting (directly explains why pandas_udf beats Python UDFs in module 05), EDA on a generated scraped-prices dataset with polars-vs-pandas taste, matplotlib fundamentals (every stats task below requires a plot). *Arc B — applied statistics (the core of the module)*: real price distributions are not normal — detecting and handling that; outliers vs parsing errors (my daily data-quality pain, formalized); confidence intervals ("mean price from 200 scraped pages — how much do we trust it"); bootstrap; A/B logic for comparing two scraping strategies; correlation vs causation trap task. Every stats task = python + mandatory visualization + a short written conclusion in NOTES.md. *Arc C — ML intro, deliberately shallow*: sklearn pipeline on the price dataset (train/test leakage trap included), feature engineering from scraped fields, then a PyTorch taste — tensors, autograd on toy examples, one small text classifier (product-category-from-title, my domain) — just enough to understand what ML engineers do with the data I prepare, and to ground module 15. NO deep learning beyond that; it's a different profession. Verification — metric thresholds on held-out data for ML tasks; for stats tasks, validator checks numeric answers, plots checked by me.

## MODULE: Module 15-llm-in-pipelines

**LLM in pipelines.** Real models, not toys: Ollama with a small model that fits 8 GB VRAM (e.g., qwen2.5:7b / llama3.1:8b quantized — pick and verify at generation time). The client interface must be swappable so a cloud API can replace Ollama with one config change (fallback if local proves too weak for a task). Tasks: structured extraction from messy HTML (where selectors fail), record classification and enrichment, dedup via embeddings (same product, different titles — use a local embedding model), mini-RAG over the sandbox's own docs. Verification — ground-truth datasets, precision/recall thresholds (set them realistically for a 7B model).

## MODULE: Module 16-testing-engineering

**Testing engineering.** Applied to my world: property-based testing with hypothesis (parser invariants), integration tests with testcontainers (Postgres, Redis), contract tests for the module 12 API, mutation testing taste. Verification is inherent — the tasks ARE tests; validator checks coverage of specified invariants.

## MODULE: Module 17-system-design

**System design (no code, but with artifacts).** 5–6 written design exercises in my context: "design a price-monitoring system for 10k sites", "storage for 5 years of price history with fast range queries", "a scraped-data delivery pipeline with client SLAs", "multi-tenant scraping platform". For each — an answer template (components, data flow, bottlenecks, evolution at 10x growth) and a "hostile interviewer questions" file for self-review. No reference designs — hints only, per the global rule.

## MODULE: Module 18-rust-track

**Rust track (I'm early in the book, independent progression, no chapter binding).** 7–8 projects mixing four flavors: *from my world* — CSV→Parquet converter (arrow-rs), multithreaded URL health checker, log parser with aggregations; *new territory* — a TUI app with ratatui (e.g., a live dashboard tailing a log file or watching a directory); *applied* — a mini key-value store with persistence (bitcask-style); *Rust-specific* — a small parser/interpreter for a toy expression language (ownership + enums + pattern matching showcase), optional proc-macro taste at the end. Each project lists the idioms it must cement (ownership, Result/?, iterators, traits, threads). No async until the last two projects. Cargo tests included per project.

## MODULE: Module 19-ts-track

**TS track (maintenance and deepening, NOT basics).** I have a production NestJS project and a personal monorepo (NestJS API + workers + scheduler + Next.js) — skip intro NestJS entirely. 3–4 tasks that deepen: advanced type system (generics with constraints, conditional/mapped types, discriminated unions, branded types) via "a type-safe SDK client for the module 12 API with zod runtime validation and types inferred from schemas"; a curated set of 10–15 type-challenges with progression; a monorepo architecture task (shared types between API/workers/web without duplication, contract-first). Focus: TS as a type and contract system, not "JS with types".

## MODULE: Module 20-kubernetes

**20 — Kubernetes (wide, easy-to-hard progression).** My real level, calibrate precisely: I deploy to k8s daily at work, but via existing charts and an Argo template — I fill in a template someone else designed, I don't design manifests or charts myself. I took a k8s course, so theory is familiar but hands-on practice is thin. So: do NOT skip fundamentals, but pace them fast (practice-first, minimal theory recaps), and build up to deep operational skills. Local cluster via kind or k3d.

Structure the module as a ladder of arcs, each arc = several single-evening tasks + the later arcs' capstones multi-evening:

**Arc 1 — Manifests from zero (foundation, fast pace).** Write raw YAML by hand, no Helm: Deployment for a provided worker app, Service, ConfigMap/Secret, liveness/readiness/startup probes (with a task where wrong probes cause a rolling-update outage — observe, then fix), resource requests/limits, a Job and a CronJob (scraper-flavored: a scheduled scrape job). Verification — validator scripts assert the deployed state and behavior (e.g., rolling update completes with zero dropped requests against a test load).

**Arc 2 — Your own Helm chart (the centerpiece — this is exactly what I currently do by template without understanding).** Take the Arc 1 manifests and grow them into a chart written from scratch: templates, values.yaml design (what should be a value vs hardcoded — design task with review checklist), helpers/_tpl, conditionals and ranges, chart dependencies, hooks, `helm template` diffing as a debug workflow. Then a task: "here is the kind of company template I fill at work (generate a realistic worker+api+queue umbrella-style template) — reverse-engineer it: explain every decision it makes, find two questionable ones." Capstone: package one of the sandbox's earlier projects (module 06 or 13) as a proper chart with configurable workers, probes, resources.

**Arc 3 — Operations & debugging.** Requests/limits from actual measurements (profile a provided workload, right-size it); OOMKill anatomy; QoS and eviction; a Pending-pod zoo (resources, affinity, taints, PVC binding — diagnose each from events alone); CrashLoopBackOff triage methodology; ephemeral containers for distroless images; capstone "production incident" — a multi-component app degraded, scripted hidden root cause, find it from symptoms.

**Arc 4 — Networking & state.** Services and kube-proxy from the inside; ingress; DNS failure debug tasks; NetworkPolicy — isolate scraper-style workers to reach only the queue and targets, verify with tests. StatefulSets vs Deployments and why databases on k8s hurt; Postgres via an operator (CloudNativePG) locally, simulate failover, observe the operator's actions.

**Arc 5 — Argo CD demystified (I use it via template — open the box).** Install Argo CD locally, deploy the Arc 2 chart through it: Application spec written by hand (not by template), sync policies, drift detection (manually mutate the cluster, watch self-heal), sync waves and hooks, app-of-apps pattern (recognize it — it's likely what my work template implements), rollback via git revert. Written task: map every field of my work's Application template to what it actually does.

**Arc 6 — Advanced (optional).** HPA on custom metrics (queue depth from RabbitMQ/redpanda — my real case), PDB vs scripted node drains, Helm vs Kustomize reasoned comparison, and an optional multi-evening capstone: a minimal operator/CRD on kopf — a `ScrapeJob` CRD that spawns worker deployments and cleans up. Enough to demystify operators, no more.

Verification style throughout: scripted broken/target states + validator scripts asserting the fixed/deployed state. Hints 1–3, no solutions — same global rules.

Also update the root README learning map and PROGRESS.md. Keep the existing `k8s-bonus/` levels in modules 06/07/13 as-is — they remain light exercises; module 20 is the real track (recommend in README doing Arc 1–2 before those bonuses).

## MODULE: Toolkit track (t1–t4)

The **toolkit track** is a family of small modules (3–5 single-evening tasks each, no capstones) about using tools well, as opposed to the main modules' engineering topics:

```
├── toolkit/
│   ├── t1-ai-assisted-engineering/
│   ├── t2-modern-python-toolchain/
│   ├── t3-cli-data-toolkit/
│   └── t4-git-advanced/
```

**t1 — AI-assisted engineering (the priority of this track).** My level: I use Claude Code daily and understand correct usage at a working level — target advanced practice, not "what is a prompt". IMPORTANT for generation: consult current Claude Code documentation while generating this module (features evolve fast); tasks must reference real, currently existing mechanisms, not invented ones. Tasks, roughly easy→hard:
1. **Project memory done right** — write a proper CLAUDE.md for this very sandbox repo (conventions, verification commands, orchestration rules); measurable goal: a fresh session solves a scripted task correctly without re-explaining context. Include guidance on what belongs in memory vs what rots.
2. **Custom subagents** — design 2–3 project subagents (e.g., a test-runner/verifier agent, a code-reviewer agent with my review checklist); task includes when NOT to delegate.
3. **Hooks & guardrails** — a hook that auto-runs the relevant module's tests after edits and blocks on failure; a formatting/lint hook (ties into t2).
4. **Headless & CI** — `claude -p` in scripts; one task wiring an AI review step into the ci-meta GitHub Actions workflow (label-triggered, not on every push).
5. **A minimal MCP server** — write a tiny Python MCP server exposing sandbox progress (reads PROGRESS.md, reports next recommended task); connect it and use it. Demystifies MCP by building one.
6. **Verification discipline** — a written+practical task on reviewing AI-generated code: I take a deliberately plausible-but-flawed generated patch (subagents: create 2–3 such patches with subtle bugs — a race, an off-by-one in pagination, a silent type coercion) and must find the flaws before "merging". This is the core skill of AI-assisted work.
Verification for t1: artifact-based where possible (hook fires, MCP server responds, CI step runs); the review task has hidden-bug ground truth.

**t2 — Modern Python toolchain.** My stack is Python-first; modernize the workflow: uv (project + tool management, replacing pip/venv habits), ruff (lint + format, custom rule config), pyright or mypy strict on a real module of the sandbox (fix what it finds — generate code with genuine typing issues), pre-commit wiring it all, packaging a small internal library properly (pyproject, src layout). Verification — CI-style check scripts must pass.

**t3 — CLI data toolkit.** One-evening tasks, each a realistic "explore/fix data from the terminal" scenario on generated files: jq on nested scraped JSON (transformations, not just filters), ripgrep/fd fluency drills, DuckDB CLI as a data swiss-knife (query a directory of Parquet/CSV in one-liners — complements module 09), hyperfine for honest micro-benchmarks, GNU parallel for a batch-processing task. Verification — expected-output checks.

**t4 — Git advanced.** Beyond daily add/commit/push: interactive rebase to clean a messy generated history, bisect to find a scripted regression (generate a repo with a hidden breaking commit), worktrees for parallel work (natural fit with AI-assisted flows — link to t1), reflog rescue task ("the branch is gone — recover it"), meaningful history design (written task: commit granularity policy). Verification — repo-state validators.

Update the root README learning map (toolkit track listed separately, "dip in anytime" — no prescribed order except t1 task 1 early, since CLAUDE.md improves all other sandbox work) and PROGRESS.md.

## MODULE: ci-meta

A GitHub Actions workflow that, on push, detects the changed module and runs its tests (service containers for Postgres/Redis/etc.). One evening; doubles as CI practice and a living progress check. Generate after all modules exist.

