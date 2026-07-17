# Conventions

Authoring rules for all current and future content in this repository. Applies to every module, every task, and every agent (human or otherwise) that generates content here.

## Task directory format

Each task is a directory named `NN-task-name/` inside its module, containing:

```
NN-task-name/
  README.md
  src/            # minimal scaffold with TODOs — the learner writes all real code
  tests/
  hints/
    hint-1.md
    hint-2.md
    hint-3.md
  NOTES.md
```

Each module additionally has, at the module root (shared across its tasks):

```
docker-compose.yml
pyproject.toml
uv.lock
```

### Task README.md must contain

- **Backstory** — why this task exists, framed as a realistic situation, not an abstract exercise.
- **What's given** — the starting state: scaffold code, seeded data, existing schema, etc.
- **What's required** — the concrete deliverable.
- **Completion criteria** — how the learner knows they're done (points to the validator/tests).
- **Estimated evenings** — a number or small range.
- **Topics to read up on** — topic names only (e.g. "B-tree vs GiST indexes," "window function frame clauses"), never links.

## Hints

- `hint-1.md` — points in a direction, no specifics.
- `hint-2.md` — narrows to a specific mechanism or approach.
- `hint-3.md` — concrete approach, close to pseudocode if needed.
- Hints never contain ready-made code or SQL that solves the task. There are **no reference solutions anywhere in this repository, ever** — not in hints, not in `.authoring/`, not in tests.

## Verification

- Every task has an objective check: a pytest suite, a standalone validator script, or a measurable metric.
- Structural checks are primary: plan shape (e.g. "no `Seq Scan` in this `EXPLAIN`"), or result correctness against a reference aggregate computed independently by the validator.
- Timing checks are always expressed relative to a machine-local baseline, never as an absolute number. A baseline script runs first, writes its result to a gitignored `*-local.json`, and later checks compare against that file.
- Validators must fail gracefully on an unsolved task: print `NOT PASSED: <reason>` and exit 1. No raw tracebacks bubbling up to the learner.

## Data generation

- All seed data is produced by deterministic scripts (numpy / Faker) with fixed random seeds — reruns must be reproducible.
- Distributions should be realistic and skewed where the real world is skewed: Zipf for popularity/access patterns, log-normal for prices/durations, seasonal/cyclical timestamps for time series.
- Every generation script respects a `SCALE` environment variable, default `1.0`, controlling row/record counts.
- Generation is vectorized (numpy/pandas, not row-by-row Python loops) and loads into Postgres via `COPY`, not row-by-row `INSERT`.
- Generated data lives under a `data/` directory inside the task or module and is **never committed** (see `.gitignore`).

## Python

- Each module has its own `pyproject.toml` and a committed `uv.lock`.
- Run everything via `uv run` (e.g. `uv run pytest`, `uv run python src/seed.py`). Do not assume a global Python environment.
- Postgres access goes through `psycopg` (v3), not `psycopg2` or an ORM, unless a task is specifically about an ORM.

## Ports

Every module gets unique, env-overridable host ports so multiple modules' `docker-compose.yml` files can run concurrently without collisions.

| Module | Service | Host port | Env var |
|---|---|---|---|
| 01-sql-foundations | Postgres | 54301 | `SANDBOX_01_PORT` |
| 02-sql-optimization | Postgres | 54302 | `SANDBOX_02_PORT` |
| 03-data-modeling | Postgres | 54303 | `SANDBOX_03_PORT` |
| 04-storage-and-formats | MinIO (API / console) | 9301 / 9302 | `SANDBOX_04_MINIO_PORT` / `SANDBOX_04_MINIO_CONSOLE_PORT` |
| 05-distributed-processing-spark | MinIO (API / console) | 9501 / 9502 | `SANDBOX_05_MINIO_PORT` / `SANDBOX_05_MINIO_CONSOLE_PORT` |
| 05-distributed-processing-spark | Spark UI | 4040 | `SANDBOX_05_SPARK_UI_PORT` |
| 06-pipelines-and-orchestration | Postgres | 54306 | `SANDBOX_06_PORT` |
| 06-pipelines-and-orchestration | Airflow UI | 8306 | `SANDBOX_06_AIRFLOW_PORT` |
| 06-pipelines-and-orchestration | MinIO (API / console) | 9601 / 9602 | `SANDBOX_06_MINIO_PORT` / `SANDBOX_06_MINIO_CONSOLE_PORT` |
| 07-streaming | Postgres | 54307 | `SANDBOX_07_PORT` |
| 07-streaming | Redpanda (Kafka API) | 19092 | `SANDBOX_07_KAFKA_PORT` |
| 07-streaming | Redpanda (Admin API) | 19644 | `SANDBOX_07_REDPANDA_ADMIN_PORT` |
| 07-streaming | Redpanda Console | 8307 | `SANDBOX_07_CONSOLE_PORT` |
| 08-cdc-debezium | Source Postgres | 54308 | `SANDBOX_08_SOURCE_PORT` |
| 08-cdc-debezium | Mart Postgres | 54318 | `SANDBOX_08_MART_PORT` |
| 08-cdc-debezium | Redpanda (Kafka API) | 19093 | `SANDBOX_08_KAFKA_PORT` |
| 08-cdc-debezium | Redpanda (Admin API) | 19645 | `SANDBOX_08_REDPANDA_ADMIN_PORT` |
| 08-cdc-debezium | Redpanda Console | 8308 | `SANDBOX_08_CONSOLE_PORT` |
| 08-cdc-debezium | Kafka Connect REST | 8383 | `SANDBOX_08_CONNECT_PORT` |
| 09-olap-clickhouse-duckdb | ClickHouse (HTTP) | 8309 | `SANDBOX_09_CH_HTTP_PORT` |
| 09-olap-clickhouse-duckdb | ClickHouse (native TCP) | 9309 | `SANDBOX_09_CH_NATIVE_PORT` |
| 09-olap-clickhouse-duckdb | Postgres | 54309 | `SANDBOX_09_PG_PORT` |
| 10-nosql-patterns | Redis (Redis Stack) | 6310 | `SANDBOX_10_REDIS_PORT` |
| 10-nosql-patterns | MongoDB | 27310 | `SANDBOX_10_MONGO_PORT` |
| 10-nosql-patterns | Postgres | 54310 | `SANDBOX_10_PG_PORT` |
| 12-api-engineering | Postgres | 54312 | `SANDBOX_12_PG_PORT` |
| 12-api-engineering | Redis | 6312 | `SANDBOX_12_REDIS_PORT` |
| 13-scraping-at-scale | Target site (HTTP) | 8313 | `SANDBOX_13_TARGET_PORT` |
| 13-scraping-at-scale | Prometheus | 9313 | `SANDBOX_13_PROM_PORT` |
| 13-scraping-at-scale | Grafana | 3313 | `SANDBOX_13_GRAFANA_PORT` |

Future modules extend this table when generated — pick the next free block (e.g. `543NN` for Postgres-based modules, module-specific ranges for others) and record it here immediately.

Exception: module 20-kubernetes uses a kind/k3d local cluster instead of docker-compose, so it has no host-port row here.

## `.authoring/` directories

Modules may contain an `.authoring/` directory holding generation notes with spoilers: planted defects, intended query plans, the reasoning behind a task's design. These are needed so a future generation session can resume or extend a module without re-deriving everything from scratch.

- `.authoring/` is committed, not gitignored.
- It is clearly marked (in the directory itself and in the module README) as off-limits for the learner to read before attempting the task.
- The learner reads it after finishing a task, if at all — it is not a solution file to consult mid-task.

## General

- All content in English, no emojis.
- Code comments are minimal — only where the logic is genuinely non-obvious or the context is load-bearing. No restating what the code already says.
