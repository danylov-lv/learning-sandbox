# Module 09 infra — live-verification notes

Wave-1 foundation build. Live-verified on Windows 11 (Docker Desktop 28.3.3,
compose v2.39.2, uv 0.10.9). These are the exact versions, gotchas, and
commands from the verification run.

## Versions (resolved by `uv sync`)

- `clickhouse/clickhouse-server:24.8` (LTS), `postgres:16`
- `clickhouse-connect==1.4.2`, `psycopg==3.3.4` (`psycopg[binary]`),
  `duckdb==1.5.4`, `pyarrow==25.0.0`, `numpy==2.5.1`, `faker==40.28.1`,
  `pytest==9.1.1`
- Python 3.12 (`.python-version`)

## Commands run

```bash
cd 09-olap-clickhouse-duckdb
docker compose up -d
# both healthy in a few seconds:
docker compose ps          # clickhouse healthy, postgres healthy
uv sync

SCALE=0.01 uv run python generate.py          # ~8s: 500k rows -> pg + ch + parquet + GT
GROUND_TRUTH_ONLY=1 SCALE=1.0 uv run python generate.py   # ~14s: 50M GT, numpy only, no DB
```

## Timings / footprint

- `SCALE=0.01` full three-sink load (500k rows): **~8s** wall.
- `GROUND_TRUTH_ONLY=1 SCALE=1.0` (50M rows, numpy only, no DB, no parquet):
  **~14s** wall. Peak memory a few GB (50M rows across ~8 tight numpy arrays:
  product_id/seller_id uint32, price float64, category/currency int8, day
  int32, plus the `rng.choice` probability temporaries). Comfortable on this
  box — no fallback to a smaller committed scale needed. **Committed
  ground-truth scale = 1.0 (50M).**

## Gotchas hit

1. **`ch_read_rows` query_id.** clickhouse-connect 1.4.2's `Client.query()`
   does NOT accept a `query_id=` kwarg (raises `TypeError`). ClickHouse reads
   `query_id` as a URL parameter, and clickhouse-connect forwards `settings`
   entries as URL params, so the working form is
   `client.query(sql, settings={"query_id": qid})`. Then `SYSTEM FLUSH LOGS`
   and select `read_rows` from `system.query_log WHERE query_id = ... AND
   type='QueryFinish'`.

2. **`SELECT count()` is not a valid full-scan baseline.** ClickHouse answers
   `count()` from part metadata (`read_rows` ≈ 0/1), so a pruning check that
   compares `count()` against a filtered `count()` is meaningless. Use an
   aggregate that forces a real column scan, e.g. `sum(price)`. Verified:
   `sum(price)` full = 500000 read_rows, `sum(price) WHERE category=<c> AND
   product_id<50` = 8192 read_rows (one granule). This is documented in
   `ch_read_rows`'s docstring and design.md so task authors don't trip on it.

3. **ClickHouse insert path = `insert_arrow`.** The generator builds one
   pyarrow Table and feeds `client.insert_arrow("observations_raw", tbl,
   database="price_history")` (sliced into 1M-row batches). This avoids
   per-row Python object conversion and maps arrow types straight to CH
   (string→LowCardinality(String), double→Float64, timestamp[s]→DateTime,
   uint32→UInt32, bool→UInt8). Same Table is reused to write the Parquet lake
   (`pyarrow.dataset.write_dataset`, hive partitioning by category) and to
   drive the Postgres `COPY` (per-batch `to_pylist()`).

4. **Coherence between committed GT and live stack.** `generate.py` rewrites
   `data/ground-truth.json` on every run to the scale it just loaded. The
   committed file must be 50M, but the live DBs here are loaded at 0.01 (fast
   verification). A verification/task wave should regenerate at its chosen
   SCALE (loads stack + matching GT), then restore the 50M GT with
   `GROUND_TRUTH_ONLY=1` before committing. Documented in README + design.md.

## Cross-engine correctness (SCALE=0.01)

- Row counts: Postgres = ClickHouse = DuckDB(parquet) = ground truth =
  500000.
- `price_sum`: pg = ch = ground truth = 36780355.61 (exact at 2 decimals).
- `per_category[electronics].count` = ch live count = 158754.
- Benchmark answer `per_category_instock[electronics]`: ground truth
  (count 135087, avg 134.6063) == live ClickHouse (135087, 134.6063).
- Pruning: `ch_read_rows` full `sum(price)` = 500000, PK-filtered = 8192.

## Stack state at handoff

`docker compose up -d` left running, both services healthy. Live DBs loaded
at SCALE=0.01 (500k rows) with a matching Parquet lake on disk. Committed
`data/ground-truth.json` is at SCALE=1.0 (50M) — the answer key; everything
else under `data/` is gitignored. `git add -n` confirms only
`data/ground-truth.json` would be staged from `data/` (parquet ignored).
