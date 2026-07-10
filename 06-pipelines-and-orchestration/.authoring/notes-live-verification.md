# Live verification pass — module 06 (session 2026-07-10)

The first session that ran the stack and validators end to end. Prior sessions
generated all task content statically; their notes list "open items for the
live pass" — this file records what that pass found and fixed. Off-limits for
learners (documents which validators pass with a correct solution and the
planted-data fixes).

## Environment confirmed

- `docker compose up -d`: all 8 services healthy (airflow-* + warehouse + minio
  + alert-sink), matching `notes-infra-docker.md`.
- Data deterministic: 14 days 2025-06-01..14; `data/ground-truth.json` present.

## Stock-fail pass (all validators, unsolved state)

Every task validator was run against the stock (unsolved) repo. All fail
cleanly — `NOT PASSED`, exit 1, no raw traceback leaking as a crash:

- 01/02/03: targeted precheck messages ("staging.price_records_raw does not
  exist — apply src/ddl.sql first").
- 04/05/06/10-cp1: caught via the `@guarded` wrapper as `NOT PASSED: unexpected
  error: UndefinedTable ...` (graceful, exit 1) — less targeted than 01-03 but
  acceptable.
- 07: static NOTES.md check ("must discuss SparkSubmitOperator").
- 09: runs the stub flow in a subprocess, reports `NOT PASSED: first run of
  flow.py exited 1` and shows the flow's NotImplementedError as captured context
  (not a validator crash).
- 10-cp2/cp3: "manifest not found / DESIGN.md not found — run the drill first".
- k8s-bonus: `helm template` renders zero manifests (templates/ empty).
- 08 (dbt): does NOT falsely pass; it shells `dbt build` against **module 02's**
  Postgres (600s subprocess timeout) and fails when that DB is absent. Its clean
  message + full pass-path require module 02's stack up (documented dependency).

## Pass-path pass (throwaway reference solutions, live stack)

Reference solutions were built in throwaway `dags/zz_ref_*.py` (deleted after),
run via `airflow dags test`, then validated host-side. Confirmed PASSED:

- **01** — 38580 rows for 2025-06-01, 155 malformed skipped.
- **02** — idempotent rerun for 2025-06-03, staging unchanged at 49269, audit +1.
- **03** — all 14 days correct; audit >=2 for repaired 06-06/07/08, >=1 else.
- **04** — quarantine + staging match GT for 2025-06-05 and the 06-15 drill day,
  rerun idempotent, alerts exact.

05/06 could not initially pass due to BUG 1 below; everything else in a correct
05/06 solution was verified working during that attempt (locale price parser
reproduces `per_day_currency` on drift days to 0.00 diff; validity split,
seller_rating, quarantine bounds, contract_drift alerts, downstream_check.sql).

07 (Spark), 08 (dbt, needs module 02), 09 (Prefect), 10 (capstone CP1-3),
k8s-bonus (needs a kind/k3d cluster + helm install for the cluster half):
stock-fail verified; full live pass-path NOT built this session.

## Bugs found and fixed this session

### BUG 1 (blocking 05, 06, and capstone 10) — FIXED

`core.price_records` has `UNIQUE (source_site, product_url, scraped_at)`, and the
05/06 validators assert `core_count == per_day.<dt>.valid_records` exactly. But
the generator produced genuinely-distinct VALID records colliding on that natural
key (same source + product + same-second scraped_at, differing price), while
`valid_records` counts byte-distinct payloads — so core collapsed ~28-157
rows/day and the equality was unsatisfiable on every day. Root cause: earlier
sessions never loaded valid records into the UNIQUE-constrained `core` (nothing
ran live), and GT deduped only byte-identical lines, never the natural key.

Fix (in `generate.py`, `resolve_valid_key_collisions`): within each day, among
VALID records only, deterministically nudge a colliding record's `scraped_at` to
the nearest free whole-second in the day window — **zero added RNG draws**, so
the entire RNG stream and every (timestamp-independent) ground-truth field are
unchanged. Applied after scraped_at assignment, before GT computation and before
byte-identical duplicate injection (so intended duplicate-of-valid collapses are
preserved). Invalid/malformed lines untouched.

Proven after regeneration at SCALE=1.0:
- `sha256(ground-truth.json)` unchanged: `b04769052d076d54a3312a9d002cf484d5882d0c6617605949a21df79c6d303e` (GT invariance — no field perturbed).
- All 14 days: distinct `(source_site, product_url, scraped_at)` among valid
  records == `valid_records` (per-day nudge counts 28-157). This is the property
  that makes `core_count == valid_records` achievable; combined with the live
  05/06 verification of everything-but-the-count, 05/06/capstone are solvable.
- Determinism preserved: two regen runs byte-identical (all 15 files).

### BUG 2 (would block every learner at task 01) — FIXED

`docker-compose.yml` bind-mounts `./logs:/opt/airflow/logs`, but `logs/` is
gitignored, so a fresh checkout has no host `./logs`. On Docker Desktop Windows
the daemon-created source mounts un-stat-able and every `airflow dags test`
aborts with `FileExistsError: '/opt/airflow/logs'` (airflow-init's in-container
`mkdir` can't repair a broken host source). Fixed by shipping `logs/.gitkeep`
(with a `.gitignore` negation) so the host dir exists on checkout.

### DDL inconsistency (`ops.quarantine.raw_line`) — FIXED

Task 04's ddl (the table's introducing task, canonical) has `raw_line text`;
task 05's had `raw_line integer`. Both use `CREATE TABLE IF NOT EXISTS`, so the
first applied wins and the other's expectation could break. Fixed 05's to `text`.

## Cleanup / stock restore

- Removed stray `data/raw/dt=2025-06-15/` (a leftover from prior testing of the
  capstone `drill_new_drift.py`, which regenerates it on demand).
- Regenerated `data/` (14 days) via the fixed generator; `ground-truth.json`
  unchanged (see BUG 1 sha).
- `docker compose down -v` (warehouse/airflow/minio volumes wiped) so a learner
  starts from a clean warehouse; emptied `data/alerts/alerts.ndjson`; cleared
  `__pycache__` and `logs/` runtime content (kept `logs/.gitkeep`).
- Confirmed `dags/` holds only `.gitkeep` + `smoke_env.py`; no `zz_ref_*` or
  scratch left in the repo.
