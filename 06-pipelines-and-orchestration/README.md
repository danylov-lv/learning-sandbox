# 06 — Pipelines and Orchestration

## Backstory

PriceWatch's scrapers dump raw NDJSON to disk every night, and until now nothing turns those dumps into anything a BI person or a pricing model can query — the closest thing to a pipeline is a cron job and a prayer. You've run queues, workers, and k8s jobs for years; what's new here is doing the work inside an orchestrator that owns scheduling, retries, and historical replay for you.

You are going to build the ETL properly on Airflow: raw scraped NDJSON → a `staging` layer → `core` serving tables, with a `mart` on top. The whole module is organised around the properties that separate a real pipeline from a script — idempotent loads, correct backfill and hole-repair, poison-record quarantine with alerting, and pandera data contracts that catch upstream schema drift at the boundary instead of downstream three days later. Two of the stages reach outside Airflow: one runs the module 05 Spark job as a scheduled pipeline stage that lands a partitioned silver lake, and a dbt mini-project builds marts over module 02's Postgres. The module closes by porting one DAG to Prefect 3 and writing down what actually differs once you've built both.

## Stack / quickstart

Prerequisites: Docker with compose v2, uv.

```bash
cd 06-pipelines-and-orchestration
uv sync
docker compose up -d
```

This brings up:

- **Airflow 3.1** (official-style compose: LocalExecutor, api-server, scheduler, dag-processor, triggerer, on its own metadata Postgres) — webserver at http://localhost:8306, login `admin` / `admin`.
- **warehouse** — a Postgres 16 on host port `54306` (db `pipelines`, user/password `sandbox`/`sandbox`), pre-seeded with schemas `staging`, `core`, `mart`, `ops`. Exposed to DAGs as the Airflow connection id `warehouse`.
- **MinIO** — S3-compatible object storage, API `9601`, console `9602` (`sandbox` / `sandbox123`); bucket `lake-06` created by a `minio-init` sidecar. Used by the Spark silver-lake stage.
- **alert-sink** — a small HTTP sink the poison-record and alerting tasks post to; delivered alerts land under `data/alerts/`.

Ports are overridable via `SANDBOX_06_PORT`, `SANDBOX_06_AIRFLOW_PORT`, `SANDBOX_06_MINIO_PORT` / `SANDBOX_06_MINIO_CONSOLE_PORT` — deliberately distinct from other modules so several stacks can run at once.

**DAG-file convention.** Each task ships its DAG skeleton under `src/`. Airflow only scans the shared module-root `dags/` folder (mounted into every Airflow container), so you *copy* each task's `src/` DAG into `dags/` and fill in its TODOs there. Task 03 reuses the `t02_incremental_load` DAG, task 06 reuses your `t05_contract_gate`, and the capstone composes several — so the DAGs accumulate in `dags/` as you go.

**Validators run host-side.** From each task directory, `uv run python tests/validate.py`. Validators read the warehouse over the exposed port (or read MinIO / the alert-sink) and, where relevant, re-trigger your DAG to assert idempotency — they don't just check the data once.

**Data.** `uv run python generate.py` writes deterministic (seed `60606`) raw dumps — one file per day under `data/raw/dt=YYYY-MM-DD/prices.ndjson` for the 14 days 2025-06-01..14 — with planted defects (malformed lines, duplicates, invalid records, late-arriving repeats, schema drift). Everything under `data/` is gitignored and disposable, except `data/ground-truth.json`, which is committed as the answer key validators check against.

## Tasks

| # | Task | Objective | Effort |
|---|------|-----------|--------|
| 01 | first-dag-raw-to-staging | Smallest slice: one DAG, one task, one day's dump into `staging` | 1 evening |
| 02 | incremental-idempotent-loads | Scheduled incremental load, idempotent per day — rerun changes nothing | 1 evening |
| 03 | backfill-and-recovery | Backfill history and repair specific holes without touching correct days | 1 evening |
| 04 | poison-records-and-alerting | Quarantine unparseable rows to a dead-letter table, alert on breakage-rate spikes, fail on missing dumps | 1 evening |
| 05 | contract-gate-pandera | A pandera contract gate from `staging` to `core`: violations quarantined, not coerced | 1 evening |
| 06 | contract-evolution | Survive two upstream schema changes without breaking downstream consumers | 1 evening |
| 07 | spark-stage-silver-lake | Run the module 05 Spark job as an Airflow-owned stage → partitioned silver lake on MinIO | 1 evening |
| 08 | dbt-marts-over-oltp | A dbt staging layer + two marts with tests, over module 02's Postgres | 1 evening |
| 09 | prefect-migration | Port the task-02 loader to a Prefect 3 flow, run it, write the honest comparison | 1 evening |
| 10 | capstone-end-to-end | Compose everything into one production pipeline: CP1 build + backfill, CP2 failure drills, CP3 design memo | multi-evening |

`k8s-bonus` is optional and carries zero capstone weight — deploying the loader as a Helm chart + CronJob on a local cluster; skip it freely, nothing else depends on it.

## Cross-module ties

- **Task 07** orchestrates the **module 05** Spark job as a pipeline stage (pyspark and the s3a jars are baked into the Airflow image, so it runs local-mode inside the Airflow container).
- **Task 08** targets **module 02's** Postgres as its dbt source — that module's stack must be up while you work task 08.

## Topics to read up on

- Airflow 3 and the TaskFlow API (data intervals, logical date, retries/replay)
- Idempotent loads and upserts (delete-insert vs merge per partition)
- Backfill semantics: loading history vs repairing specific holes
- Dead-letter / quarantine patterns and alerting thresholds
- pandera contracts as pipeline-boundary gates, and schema evolution without breaking consumers
- dbt staging/marts layering and tests
- Prefect vs Airflow execution models (scheduler, workers, deployment ceremony)

## How to work

Per-task `README.md` holds the backstory and completion criteria; `src/` has the scaffolds you fill in; `tests/validate.py` grades it; `NOTES.md` is your post-task writeup (several tasks require sections in it). `.authoring/` contains spoilers — don't read it before finishing a task.
