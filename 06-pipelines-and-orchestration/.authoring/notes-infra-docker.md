# Infra notes: docker-compose for 06-pipelines-and-orchestration

Off-limits for learners before they attempt the tasks — this is authoring/ops context, not a
solution file. Covers the docker-compose stack only (Part 2); the generation harness and task
content are documented elsewhere.

## Pinned versions

- `apache/airflow:3.1.0` (verified pullable via `docker manifest inspect`). Base OS: Debian 12
  (bookworm), Python 3.12.11, default user `airflow` (uid 50000, gid 0).
- `postgres:16` for both the Airflow metadata db and the `warehouse` service.
- `minio/minio:latest` + `minio/mc:latest`, matching the credential/bucket convention from
  modules 04/05 (`sandbox` / `sandbox123`, one-shot `mc` init container).
- `python:3.12-slim` for `alert-sink` (stdlib only, no pip installs).
- pyspark `3.5.*` (resolved to 3.5.8 at build time) inside the custom Airflow image.
- `hadoop-aws-3.3.4.jar` + `aws-java-sdk-bundle-1.12.262.jar`, pre-fetched from Maven Central
  into pyspark's bundled `jars/` dir
  (`/home/airflow/.local/lib/python3.12/site-packages/pyspark/jars/`) at image build time.
  3.3.4 is the Hadoop client version pyspark 3.5.x ships against; 1.12.262 is the AWS SDK build
  `hadoop-aws:3.3.4` was compiled against. This gives working `s3a://` support with zero network
  access needed at spark-submit time (no `--packages` resolution at runtime).
- `openjdk-17-jre-headless` (Debian bookworm package) installed as root in the custom image for
  Spark local-mode execution.

## Auth manager choice

Airflow 3's new `SimpleAuthManager` is the "intended" lightweight dev auth path, but as of
3.1.0 it does not reliably honor a fixed, non-random admin password via environment variables
(known limitation — see apache/airflow discussion #59514). For predictable admin/admin login in
a learning sandbox, this stack uses the well-tested `FabAuthManager`
(`airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager`, bundled in the base
image) with `_AIRFLOW_WWW_USER_USERNAME=admin` / `_AIRFLOW_WWW_USER_PASSWORD=admin` set in
`airflow-init`. This is the same mechanism the official Airflow docker-compose reference uses.
Login: **admin / admin**.

## Gotchas

- `docker compose build` with `build:` duplicated across services via the `x-airflow-common`
  YAML anchor raced when the shared image tag (`sandbox-06-airflow:local`) didn't exist yet —
  concurrent builds all tried to `naming to image` the same tag and one lost with
  "image already exists". Fix: build one Airflow service first
  (`docker compose build airflow-init`) to populate the tag, then `docker compose build` for the
  rest hits cache and finishes cleanly. Only matters on a cold cache / first build.
- The Airflow 3 entrypoint script intercepts unknown first args as `airflow` subcommands, so
  `docker run --entrypoint bash apache/airflow:3.1.0 -c "..."` is needed to poke around inside
  the base image (plain `docker run image cat ...` fails with an "invalid choice" error from the
  `airflow` CLI, not a shell error).
- `airflow.sdk` (not `airflow.decorators`) is the TaskFlow API surface in Airflow 3 — verified
  importable in the pinned image before writing `smoke_env.py`.
- Fixed Fernet key is a throwaway dev value baked into `docker-compose.yml` — regenerate before
  ever reusing this compose file outside a sandbox.

## Startup timing

(measured on Windows 11 + Docker Desktop, `docker compose up -d` with a warm build cache — i.e.
images already built)

- All containers `Created` and started within ~5s of issuing `up -d`.
- `airflow-postgres` and `minio` report healthy within ~1s (fast healthchecks, no real init work).
- `airflow-init` (db migrate + FAB permission sync + admin user creation) takes ~15-20s, then exits 0.
- `airflow-api-server` / `scheduler` / `dag-processor` / `triggerer` report healthy roughly 15-30s
  after `airflow-init` completes (their own healthcheck `start_period` is 30s).
- End-to-end, cold `up -d` to "everything healthy" is under 60s on this machine.
- Image build from scratch (no cache) takes a few minutes, dominated by the `apt-get install
  openjdk-17-jre-headless` layer and the pyspark pip install; the two jar `curl` downloads add
  under 10s combined.

## Fast iteration loop: `airflow dags test`

`airflow dags test <dag_id> <logical_date>` runs a DAG **in-process**, ignoring the scheduler
and DAG-file-processor polling interval entirely — no waiting for the scheduler to notice a new
or edited DAG file. This is the loop learners (and validators) should use while iterating on a
DAG: edit `dags/*.py`, then from inside any Airflow container:

```
docker compose exec airflow-scheduler airflow dags test smoke_env 2025-06-01
```

It still talks to the real metadata db and any connections configured (e.g. `AIRFLOW_CONN_WAREHOUSE`),
so it is a faithful run of task logic, just without scheduling latency. It is not a substitute
for confirming a DAG is *discovered and parses cleanly* by the dag-processor — do that separately
via the UI or `airflow dags list`.

## alert-sink contract

- Internal only, no host port. From any container on the compose network:
  `POST http://alert-sink:8000/alert` with a JSON body — each call appends one NDJSON line.
  `GET http://alert-sink:8000/health` returns 200 for liveness checks.
- On the host, the file lands at `06-pipelines-and-orchestration/data/alerts/alerts.ndjson`
  (bind-mounted from `./data/alerts` → `/alerts` in the container). `data/` is gitignored at the
  repo root (`**/data/`).

## Verification results

All PASS, run 2026-07-09:

- `docker compose build` — all 5 images (4 airflow-* services sharing one build + alert-sink)
  built clean. Hit a one-time race on cold cache: parallel `build:` targets sharing the
  `sandbox-06-airflow:local` tag via the `x-airflow-common` anchor collided on "naming to image"
  (see Gotchas). Building `airflow-init` alone first, then `docker compose build` again, fixed it.
- `docker compose up -d` — all containers reached `Created`/`Started`; `airflow-postgres`,
  `warehouse`, `minio`, `alert-sink` reported `healthy`; `airflow-init` ran migrate + admin user
  creation and exited 0; `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor`,
  `airflow-triggerer` all reached `healthy`.
- Airflow UI: `curl http://localhost:8306/login` → HTTP 200. PASS.
- Warehouse: `docker exec ... psql -U sandbox -d pipelines -c "\dn"` shows schemas `core`,
  `mart`, `ops`, `staging`, `public`. PASS.
- MinIO: bucket `lake-06` created by `minio-init` (log: "Bucket created successfully
  `local/lake-06`", "bucket lake-06 ready"). PASS.
- alert-sink: `GET /health` → 200 from inside the container. PASS.
- `airflow dags list-import-errors` — no data found (smoke_env.py parses cleanly). PASS.
- `airflow dags test smoke_env 2025-06-01` — DagRun finished with `state=success`; all three
  tasks (`check_spark`, `check_alert_sink`, `check_warehouse`) succeeded. `check_spark` ran
  `spark.range(10).count() == 10` locally and wrote/read a 5-row parquet dataset round-trip to
  `s3a://lake-06/smoke_env/roundtrip` (verified independently afterward via `mc ls` inside the
  minio container: `_SUCCESS` + 2 parquet part files present). PASS.
- Alert file on host: `data/alerts/alerts.ndjson` contains the line
  `{"source": "smoke_env", "level": "info"}` written by the `check_alert_sink` task. PASS.
- `docker compose down` (no `-v`) — all containers and the network removed; named volumes
  (`airflow-postgres-data`, `warehouse-data`, `minio-data`) survived, confirmed via
  `docker volume ls`. PASS.
