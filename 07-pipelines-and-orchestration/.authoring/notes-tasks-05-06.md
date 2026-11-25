# Authoring notes: tasks 05 (contract-gate-pandera) and 06 (contract-evolution)

SPOILERS — learner off-limits until both tasks are done. Companion to
`design.md`; read that first for the planted-drift mechanics and ground-truth
shape.

## Intended solution shapes

### Task 05

- `contracts.py`: `pandera.pandas.DataFrameSchema` with `strict=True`,
  `coerce=True`; all eight payload fields required and non-null; `currency`
  `isin {USD, EUR, GBP}`; `product_url` non-null plus a pattern like
  `^/products/p-\d{5}-[a-z-]+$`; `price > 0` plus a **per-category** absurdity
  ceiling (see below); `scraped_at` within `[dt, dt+1)`, which needs either a
  schema factory taking `dt` or a post-validate mask (both fine).
- The `scraped_at`-window and price-vs-category-ceiling rules are
  cross-column / parameterized, so they can't be plain per-`Column` `Check`s;
  the intended shapes are a DataFrame-level `Check` or a mask outside the
  schema whose failures are folded into the same quarantine path. Hints 2/3
  say this explicitly.
- DAG `t05_contract_gate` (skeleton given in `src/dag_t05_contract_gate.py`,
  learner copies to `dags/`, per the module DAG-file convention):
  extract (staging rows for `dt`, ordered by `line_no`) -> normalize jsonb
  to typed frame -> `validate(..., lazy=True)` -> split passing/failing via
  `SchemaErrors.failure_cases` row indices -> `INSERT ... ON CONFLICT
  (source_site, product_url, scraped_at) DO NOTHING` into core (this alone
  gives both rerun idempotency and duplicate-line collapse) -> quarantine
  failing rows with `stage='contract'`, idempotent via delete-then-insert
  scoped to `(dt, stage)` or an upsert on `(dt, stage, line_no)`.
- Input is the t02-loaded staging (ALL parseable lines, including
  schema-invalid records and byte-identical duplicate lines; malformed lines
  never parse so never reach staging). Stated explicitly in the README so the
  gate has something to catch. Duplicate lines exist as distinct
  `(dt, line_no)` staging rows.

### Per-category absurdity ceiling — load-bearing design fact

A flat ceiling is IMPOSSIBLE on this data, verified empirically: planted
absurd prices are `uniform(10, 20) x per-category p99`, and the dataset's
max legitimate electronics price (~5.9k) exceeds the min absurd grocery
price (~214). Per category there is a wide clean gap between the legitimate
tail and the junk cluster (min-absurd / max-valid ratio ranges 1.65x
(electronics) to 4.9x (pet-supplies), all 14 days pooled). Any per-category
ceiling inside the gap is correct; the learner is expected to eyeball or
quantile the per-category distributions from staging data. An earlier draft
of the task said a flat ceiling was fine — that was wrong and has been
fixed in README / contracts.py skeleton / hint-3.

Gap table (all 14 days, after removing other invalid classes; ceiling must
land between max_valid and min_absurd):

| category | max valid | min absurd |
|---|---|---|
| electronics | 5932 | 9812 |
| home-goods | 871 | 2308 |
| kitchen | 405 | 1417 |
| toys | 306 | 1018 |
| sporting-goods | 1046 | 2835 |
| office-supplies | 106 | 512 |
| beauty | 169 | 652 |
| grocery | 46 | 214 |
| pet-supplies | 120 | 593 |
| tools | 512 | 2230 |
| furniture | 5447 | 16992 |
| apparel | 320 | 1248 |

### Task 06

- No new DAG id: the learner evolves `t05_contract_gate` and its
  `contracts.py` in place. Story beats: run 06-10 -> strict schema rejects
  every row on the unexpected `seller_rating` column -> detect
  batch-level drift (same `(column, check)` failure hitting ~100% of rows,
  vs the normal sub-2% row-level rate) -> alert + quarantine-or-halt, never
  a partial load -> v2 schema adds optional nullable `seller_rating` ->
  run 06-12 -> every row fails price dtype/coercion -> same drift response
  -> v3 adds a pre-validation normalizer parsing both locale price formats
  -> downstream_check.sql (given) still works untouched -> backfill
  06-06..06-14.
- Price-format disambiguation rule (verified to reproduce ground truth
  exactly): every drift-B string either starts with a currency symbol
  (`$`, `€`, `£` -> US style: strip symbol, drop `,` thousands, `.` is the
  decimal separator) or ends with a 3-letter ISO code (`USD`/`EUR`/`GBP` ->
  EU style: strip code, drop `.` thousands, `,` -> `.` decimal). The marker
  is always present and unambiguous — never infer the convention from
  separators alone. Plain JSON numbers pass through untouched (invalid
  records' `bad_price` stays numeric on every day, per design.md).
  Hint-3 spells this rule out in prose (allowed: hint-3 may be
  close-to-pseudocode; there is still no code given).
- `src/downstream_check.sql` is GIVEN (allowed — it's a consumer stand-in,
  not a solution): per-day per-category count/avg/min/max over
  `core.price_records`, no `seller_rating` reference.

## Validator logic and ground-truth keys used

Both validators: `uv run python tests/validate.py` from the task dir,
`sys.path` shim two levels up to import `harness.common`, everything
wrapped in `@guarded`, `PGCONNECT_TIMEOUT=5` set via `os.environ.setdefault`
before connecting (without it, a dead warehouse port hangs for minutes on
Windows instead of failing fast; with it, docker-down yields
`NOT PASSED: could not connect ...` + exit 1 in ~10 s).

### Task 05 validator (`05-contract-gate-pandera/tests/validate.py`)

Days 2025-06-01..05:
- `core.price_records` count per day == `per_day.<dt>.valid_records`.
- Per-currency `count(*)` and `sum(price)` vs `per_day_currency.<dt>.<CUR>`
  (`count` exact, `price_sum` tolerance 0.02).
- `ops.quarantine` where `stage='contract'` per day:
  `invalid_records.total <= n <= invalid_records.total + duplicate_lines`.
  Bounds instead of equality because a duplicate line can duplicate an
  invalid line (quarantined twice unless the learner dedupes — both
  behaviors are acceptable), while core dedup is forced by the UNIQUE
  constraint either way.
- Idempotency: snapshot (core, quarantine) counts for 2025-06-03, rerun via
  `docker compose exec -T airflow-scheduler airflow dags test
  t05_contract_gate 2025-06-03` (cwd = module root, 300 s timeout,
  OSError/Timeout -> NOT PASSED), snapshot again, require equality.

### Task 06 validator (`06-contract-evolution/tests/validate.py`)

All 14 days 2025-06-01..14:
- Same count + per-currency sum checks as task 05 but for every day,
  including 06-12..14 — passing the sum check there is only possible if the
  locale parser is correct (verified: an independent reimplementation of
  the full rule set + parser reproduces `per_day_currency` exactly, all
  days, counts exact and sums within 0.02).
- `seller_rating`: 0 non-null rows for dt < 2025-06-10; non-null share
  >= 0.95 for dt >= 2025-06-10 (generator plants it on 100% of valid rows,
  0.95 leaves slack for edge handling).
- Quarantine bounds re-checked for all 14 days — catches drift-valid rows
  left in quarantine after evolution (they'd blow the upper bound).
- Alerts: `read_alerts()` from harness; require >= 1 alert with
  `type == "contract_drift"` mentioning `2025-06-10` and >= 1 mentioning
  `2025-06-12` (substring search over the JSON-dumped body, so nested `dt`
  still matches), each with at least one descriptive field beyond
  `type`/`dt` (string > 3 chars, or non-empty dict/list).
- `src/downstream_check.sql` executed verbatim via psycopg; must yield
  >= 1 row for every one of the 14 distinct `dt` values.

### Ground-truth identities sanity-checked this session

Against `data/ground-truth.json` (throwaway scripts, deleted; per_day_currency
key had landed):
- `total_lines == malformed + duplicates + valid + invalid.total` — all 14 days.
- Invalid reason split sums to `invalid_records.total` — all 14 days.
- `sum over currencies of per_day_currency.<dt>.<CUR>.count ==
  per_day.<dt>.valid_records` — all 14 days.
- `per_day_currency` agrees with `global.mart_reference` (counts everywhere;
  sums within 0.02 pre-drift; mart_reference has no sums on/after 06-12 by
  design, per_day_currency has them for all days).
- Independent end-to-end recompute from raw NDJSON (dedup byte-identical
  lines, apply all validity rules with per-category `10 x p99` ceilings from
  design.md profiles, parse locale prices with the rule above) reproduces
  `per_day_currency` exactly for all 14 days. This simultaneously proves the
  drift-day formatted strings encode exactly the planted 2-decimal numerics.

## Open items for the live verification pass (docker up)

1. Nothing has been run against a live stack this session (constraint: no
   compose up/down). Needs a full walkthrough: t02-style staging load for
   the days involved (tasks 05/06 assume staging is already populated by
   earlier tasks — confirm the earlier tasks' loaders exist and their README
   tells the learner to have run them; task 05's README states the
   assumption but a live check should confirm the staging DDL/PK matches
   `src/ddl.sql`).
2. Solve task 05 for real once (reference implementation kept out of the
   repo) to confirm: pandera 0.32.1 `strict=True` failure_cases shape for
   an unexpected column (`check == "column_in_schema"` variant naming),
   coercion failure reporting for string prices, and that the
   quarantine-bounds logic matches what a straightforward solution produces.
3. Confirm `airflow dags test` on `t05_contract_gate` picks up the logical
   date as the partition day with the DAG skeleton's TaskFlow shape
   (learners read `dag_run.logical_date` / context — skeleton hints at it
   without prescribing the exact accessor).
4. Task 05 validator's rerun check invokes docker compose from the module
   root via `subprocess` — verify output capture and the 300 s timeout are
   adequate on a warm stack (a ~40k-row day through pandas + pandera should
   be well under a minute).
5. Alert-sink path: confirm a drift alert POSTed from inside a `dags test`
   run lands in `data/alerts/alerts.ndjson` on the host (smoke_env already
   proved the mechanism; re-confirm with the contract_drift body).
6. If the live pass regenerates data at a different SCALE, the absurdity-gap
   table above shifts (gap boundaries are dataset realizations, not
   constants); the per-category-gap *property* holds at any scale, but
   re-derive the table if quoted anywhere learner-visible (it isn't today).
