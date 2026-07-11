"""Deterministic generator for module 09 (OLAP: ClickHouse + DuckDB).

Builds a large scraped-price-history corpus — one fact table
`price_history.observations` — and materializes it into three places so the
module's tasks can compare engines over the same data:

  * Postgres  (`price_history.observations`, row store, index-light)
  * ClickHouse(`price_history.observations_raw`, MergeTree, sparse index)
  * a Hive-partitioned Parquet lake under `data/parquet/category=<x>/`
    (DuckDB reads this directly, zero server)

Also writes `data/ground-truth.json` (COMMITTED), the answer key every
validator grades against — computed purely in numpy, independent of any DB.

Deterministic: a single seeded `np.random.default_rng(90909)` stream with a
fixed draw order (documented in .authoring/design.md — do not reorder without
regenerating and updating every consumer). Respects `SCALE` (env, default
1.0 => 50,000,000 observation rows).

GROUND_TRUTH_ONLY=1 computes and writes ONLY ground-truth.json from the numpy
arrays, touching no database and writing no parquet — this is the fast path
used to regenerate the committed scale-1.0 answer key without the heavy load.

Idempotent: TRUNCATE/DROP+recreate everything it loads.

Usage:
    uv run python generate.py                       # SCALE=1.0 (50M rows, HEAVY)
    SCALE=0.02 uv run python generate.py            # light local run (~1M rows)
    GROUND_TRUTH_ONLY=1 uv run python generate.py   # rewrite answer key only, fast
"""

import json
import math
import os
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

MODULE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    DATA_DIR,
    GROUND_TRUTH_PATH,
    PARQUET_DIR,
    ch_client,
    pg_connect,
)

SEED = 90909

N_OBS_BASE = 50_000_000
N_PRODUCTS_BASE = 300_000
N_SELLERS_BASE = 800

IN_STOCK_P = 0.85

DATE_END = date(2025, 6, 30)
N_DAYS = 180
DATE_START = DATE_END - timedelta(days=N_DAYS - 1)

CATEGORIES = [
    "electronics", "home-goods", "kitchen", "toys",
    "sporting-goods", "office-supplies", "beauty", "apparel",
]

CATEGORY_PRICE_PROFILE = {
    "electronics": (120.0, 0.9),
    "home-goods": (45.0, 0.7),
    "kitchen": (35.0, 0.6),
    "toys": (25.0, 0.6),
    "sporting-goods": (55.0, 0.7),
    "office-supplies": (15.0, 0.5),
    "beauty": (20.0, 0.5),
    "apparel": (30.0, 0.6),
}

CURRENCIES = ["USD", "EUR", "GBP"]
CURRENCY_WEIGHTS = [0.60, 0.25, 0.15]

DRIFT_SIGMA = 0.15   # per-product log-linear price drift over the window
NOISE_SIGMA = 0.05   # per-observation log-price jitter

CH_BATCH_ROWS = 1_000_000
PG_COPY_BATCH = 200_000


def category_weights():
    """Zipf popularity over categories: rank 0 (electronics) most popular."""
    ranks = np.arange(len(CATEGORIES))
    w = 1.0 / (ranks + 1) ** 1.1
    return w / w.sum()


def day_weights():
    """Mild daily cyclicality over the 180-day window: a weekly rhythm
    (weekends scraped a little harder) plus a gentle upward trend. Normalized
    to a probability vector over day indices 0..N_DAYS-1."""
    days = np.arange(N_DAYS)
    dow = (DATE_START.weekday() + days) % 7
    weekly = np.where(dow >= 5, 1.15, 1.0)
    trend = 1.0 + 0.15 * (days / (N_DAYS - 1))
    w = weekly * trend
    return w / w.sum()


def _build(scale, rng, with_timestamps):
    """Draw the full corpus as numpy arrays. Fixed draw order (see design.md).
    `with_timestamps` also materializes the datetime64 scraped_at column
    (skipped on the GROUND_TRUTH_ONLY path, which never loads a DB)."""
    n_obs = max(1, int(round(N_OBS_BASE * scale)))
    n_products = max(1, int(round(N_PRODUCTS_BASE * scale)))
    n_sellers = max(1, int(round(N_SELLERS_BASE * scale)))

    # --- Product universe (draw order U1..U4) ---
    cat_w = category_weights()
    product_category_idx = rng.choice(len(CATEGORIES), size=n_products, p=cat_w)  # U1

    popularity_rank = rng.permutation(n_products) + 1                             # U2
    pop_weight = 1.0 / popularity_rank ** 1.07
    pop_weight = pop_weight / pop_weight.sum()

    medians = np.array([CATEGORY_PRICE_PROFILE[c][0] for c in CATEGORIES])
    sigmas = np.array([CATEGORY_PRICE_PROFILE[c][1] for c in CATEGORIES])
    z_base = rng.normal(size=n_products)                                          # U3
    log_base = np.log(medians[product_category_idx]) + sigmas[product_category_idx] * z_base
    drift_slope = rng.normal(0.0, DRIFT_SIGMA, size=n_products)                   # U4

    # --- Observations (draw order O1..O7) ---
    product_id = rng.choice(np.arange(1, n_products + 1), size=n_obs, p=pop_weight)  # O1
    seller_id = rng.integers(1, n_sellers + 1, size=n_obs)                           # O2
    currency_idx = rng.choice(len(CURRENCIES), size=n_obs, p=CURRENCY_WEIGHTS)       # O3
    in_stock = rng.random(n_obs) < IN_STOCK_P                                        # O4
    day = rng.choice(N_DAYS, size=n_obs, p=day_weights())                            # O5
    second = rng.integers(0, 86400, size=n_obs)                                      # O6
    noise = rng.normal(0.0, NOISE_SIGMA, size=n_obs)                                 # O7

    pidx = product_id - 1
    category_idx = product_category_idx[pidx].astype(np.int8)
    day_norm = (day - (N_DAYS - 1) / 2.0) / (N_DAYS / 2.0)
    log_price = log_base[pidx] + drift_slope[pidx] * day_norm + noise
    price = np.round(np.exp(log_price), 2)
    np.clip(price, 0.5, None, out=price)

    scraped_at = None
    if with_timestamps:
        base = np.datetime64(DATE_START.isoformat(), "s")
        scraped_at = base + day.astype("timedelta64[D]") + second.astype("timedelta64[s]")

    return {
        "n_obs": n_obs,
        "n_products": n_products,
        "n_sellers": n_sellers,
        "observation_id": np.arange(1, n_obs + 1, dtype=np.uint64),
        "product_id": product_id.astype(np.uint32),
        "seller_id": seller_id.astype(np.uint32),
        "category_idx": category_idx,
        "currency_idx": currency_idx.astype(np.int8),
        "price": price,
        "in_stock": in_stock,
        "day": day.astype(np.int32),
        "scraped_at": scraped_at,
    }


def _ground_truth(scale, a):
    n_obs = a["n_obs"]
    cat_idx = a["category_idx"]
    price = a["price"]
    in_stock = a["in_stock"]
    day = a["day"]
    n_cat = len(CATEGORIES)

    date_strs = [(DATE_START + timedelta(days=int(d))).isoformat() for d in range(N_DAYS)]

    cat_count = np.bincount(cat_idx, minlength=n_cat)
    cat_sum = np.bincount(cat_idx, weights=price, minlength=n_cat)
    is_mask = in_stock
    cat_count_is = np.bincount(cat_idx[is_mask], minlength=n_cat)
    cat_sum_is = np.bincount(cat_idx[is_mask], weights=price[is_mask], minlength=n_cat)

    per_category = {}
    per_category_instock = {}
    for ci, cat in enumerate(CATEGORIES):
        c = int(cat_count[ci])
        s = round(float(cat_sum[ci]), 2)
        per_category[cat] = {
            "count": c,
            "price_sum": s,
            "avg": round(float(cat_sum[ci] / c), 4) if c else 0.0,
        }
        cis = int(cat_count_is[ci])
        sis = round(float(cat_sum_is[ci]), 2)
        per_category_instock[cat] = {
            "count": cis,
            "price_sum": sis,
            "avg": round(float(cat_sum_is[ci] / cis), 4) if cis else 0.0,
        }

    day_count = np.bincount(day, minlength=N_DAYS)
    per_day_count = {date_strs[d]: int(day_count[d]) for d in range(N_DAYS)}

    combo = day.astype(np.int64) * n_cat + cat_idx.astype(np.int64)
    combo_count = np.bincount(combo, minlength=N_DAYS * n_cat)
    combo_sum = np.bincount(combo, weights=price, minlength=N_DAYS * n_cat)
    daily_category = {}
    for d in range(N_DAYS):
        for ci, cat in enumerate(CATEGORIES):
            k = d * n_cat + ci
            cnt = int(combo_count[k])
            if cnt:
                daily_category[f"{date_strs[d]}|{cat}"] = {
                    "count": cnt,
                    "price_sum": round(float(combo_sum[k]), 2),
                }

    seller_count = np.bincount(a["seller_id"], minlength=a["n_sellers"] + 1)
    order = np.argsort(seller_count)[::-1]
    top_sellers = []
    for sid in order:
        if sid == 0:
            continue
        top_sellers.append([int(sid), int(seller_count[sid])])
        if len(top_sellers) >= 10:
            break

    return {
        "seed": SEED,
        "scale": scale,
        "n_observations": n_obs,
        "n_products": a["n_products"],
        "n_sellers": a["n_sellers"],
        "categories": CATEGORIES,
        "date_start": DATE_START.isoformat(),
        "date_end": DATE_END.isoformat(),
        "n_days": N_DAYS,
        "row_counts": {"observations": n_obs},
        "price_sum": round(float(price.sum()), 2),
        "in_stock_count": int(in_stock.sum()),
        "distinct_products_with_observations": int(np.unique(a["product_id"]).size),
        "per_category": per_category,
        "per_category_instock": per_category_instock,
        "per_day_count": per_day_count,
        "daily_category": daily_category,
        "top_sellers_by_count": top_sellers,
    }


def _arrow_table(a):
    import pyarrow as pa

    cat_names = np.array(CATEGORIES, dtype=object)[a["category_idx"]]
    cur_names = np.array(CURRENCIES, dtype=object)[a["currency_idx"]]
    return pa.table({
        "observation_id": pa.array(a["observation_id"]),
        "product_id": pa.array(a["product_id"]),
        "seller_id": pa.array(a["seller_id"]),
        "category": pa.array(cat_names, type=pa.string()),
        "currency": pa.array(cur_names, type=pa.string()),
        "price": pa.array(a["price"], type=pa.float64()),
        "in_stock": pa.array(a["in_stock"], type=pa.bool_()),
        "scraped_at": pa.array(a["scraped_at"], type=pa.timestamp("s")),
    })


def _load_postgres(table):
    conn = pg_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS price_history")
            cur.execute("DROP TABLE IF EXISTS price_history.observations")
            cur.execute("""
                CREATE TABLE price_history.observations (
                    observation_id BIGINT PRIMARY KEY,
                    product_id     INTEGER NOT NULL,
                    seller_id      INTEGER NOT NULL,
                    category       TEXT NOT NULL,
                    currency       TEXT NOT NULL,
                    price          NUMERIC(12, 2) NOT NULL,
                    in_stock       BOOLEAN NOT NULL,
                    scraped_at     TIMESTAMP NOT NULL
                )
            """)
            conn.commit()

            cols = ["observation_id", "product_id", "seller_id", "category",
                    "currency", "price", "in_stock", "scraped_at"]
            n = table.num_rows
            copy_sql = f"COPY price_history.observations ({', '.join(cols)}) FROM STDIN"
            for lo in range(0, n, PG_COPY_BATCH):
                batch = table.slice(lo, PG_COPY_BATCH)
                colvals = [batch.column(c).to_pylist() for c in cols]
                with cur.copy(copy_sql) as copy:
                    for row in zip(*colvals):
                        copy.write_row(row)
            conn.commit()
    finally:
        conn.close()


def _load_clickhouse(table):
    client = ch_client()
    try:
        client.command("CREATE DATABASE IF NOT EXISTS price_history")
        client.command("DROP TABLE IF EXISTS price_history.observations_raw")
        client.command("""
            CREATE TABLE price_history.observations_raw (
                observation_id UInt64,
                product_id     UInt32,
                seller_id      UInt32,
                category       LowCardinality(String),
                currency       LowCardinality(String),
                price          Float64,
                in_stock       UInt8,
                scraped_at     DateTime
            )
            ENGINE = MergeTree
            ORDER BY (category, product_id, scraped_at)
        """)
        n = table.num_rows
        for lo in range(0, n, CH_BATCH_ROWS):
            client.insert_arrow(
                "observations_raw",
                table.slice(lo, CH_BATCH_ROWS),
                database="price_history",
            )
    finally:
        client.close()


def _write_parquet(table):
    import pyarrow.dataset as ds

    if PARQUET_DIR.exists():
        shutil.rmtree(PARQUET_DIR)
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    ds.write_dataset(
        table,
        base_dir=str(PARQUET_DIR),
        format="parquet",
        partitioning=["category"],
        partitioning_flavor="hive",
        existing_data_behavior="overwrite_or_ignore",
    )


def generate():
    scale = float(os.environ.get("SCALE", "1.0"))
    ground_truth_only = os.environ.get("GROUND_TRUTH_ONLY", "") not in ("", "0", "false")
    rng = np.random.default_rng(SEED)

    print(f"SCALE={scale} GROUND_TRUTH_ONLY={ground_truth_only}")
    a = _build(scale, rng, with_timestamps=not ground_truth_only)
    print(f"built arrays: n_obs={a['n_obs']} n_products={a['n_products']} n_sellers={a['n_sellers']}")

    gt = _ground_truth(scale, a)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_PATH.write_text(json.dumps(gt, indent=2), encoding="utf-8")
    print(f"ground truth written: {GROUND_TRUTH_PATH}")
    print(f"  n_observations={gt['n_observations']} price_sum={gt['price_sum']} "
          f"in_stock_count={gt['in_stock_count']}")

    if ground_truth_only:
        print("GROUND_TRUTH_ONLY: skipped Postgres / ClickHouse / parquet load")
        return

    table = _arrow_table(a)

    print("loading Postgres ...")
    _load_postgres(table)
    print("loading ClickHouse ...")
    _load_clickhouse(table)
    print("writing parquet lake ...")
    _write_parquet(table)
    print(f"loaded {a['n_obs']} observations into Postgres + ClickHouse + parquet at {PARQUET_DIR}")


def build_duplicate_batch(seed, n):
    """Deterministic dedup fixture for the ReplacingMergeTree task (03).

    Pure function — numpy only, touches no database — mirroring the spirit of
    module 08's build_workload. Returns a list of `n` synthetic observation
    rows in which the natural key (product_id, seller_id, scraped_at) COLLIDES
    across multiple rows, each collision carrying a distinct `version` and a
    matching `ingested_at` ordering.

    Contract for the validator: group the returned rows by
    (product_id, seller_id, scraped_at); within each group the row with the
    highest `version` is the survivor a ReplacingMergeTree(version) must keep
    after a FINAL merge, and its `price` / `in_stock` are that key's current
    values. `ingested_at` increases with `version` (a later ingest = a newer
    version), so ordering by either yields the same winner. Rows are returned
    in ingest order (ascending ingested_at), NOT grouped by key, so a naive
    insert reproduces a realistic out-of-order duplicate stream.

    Each row is a dict:
      {"product_id": int, "seller_id": int, "scraped_at": datetime,
       "category": str, "currency": str, "price": float, "in_stock": bool,
       "version": int, "ingested_at": datetime}

    product_id/seller_id are drawn from the SCALE=1.0 universe
    (1..N_PRODUCTS_BASE, 1..N_SELLERS_BASE); `category` is a fixed function of
    product_id so a product never changes category across its duplicates.
    Prices come from a generic lognormal (median 40, sigma 0.6), deliberately
    category-agnostic — this is a synthetic dedup stream, not a second
    realistic corpus.
    """
    rng = np.random.default_rng(seed)
    n = max(1, int(n))
    n_keys = max(1, n // 3)

    key_product = rng.integers(1, N_PRODUCTS_BASE + 1, size=n_keys)
    key_seller = rng.integers(1, N_SELLERS_BASE + 1, size=n_keys)
    key_day = rng.integers(0, N_DAYS, size=n_keys)
    key_second = rng.integers(0, 86400, size=n_keys)

    row_key = rng.integers(0, n_keys, size=n)
    seq = rng.random(n)
    price = np.round(rng.lognormal(math.log(40.0), 0.6, size=n), 2)
    in_stock = rng.random(n) < IN_STOCK_P
    currency_idx = rng.choice(len(CURRENCIES), size=n, p=CURRENCY_WEIGHTS)

    # version per row = rank of seq within its key group (1-based)
    version = np.zeros(n, dtype=np.int64)
    order = np.lexsort((seq, row_key))
    sorted_key = row_key[order]
    group_start = np.concatenate(([True], sorted_key[1:] != sorted_key[:-1]))
    ranks = np.arange(n) - np.maximum.accumulate(np.where(group_start, np.arange(n), 0))
    version[order] = ranks + 1

    base_ingest = datetime(2025, 7, 1, 0, 0, 0)
    rows = []
    for i in range(n):
        k = int(row_key[i])
        scraped = datetime.combine(DATE_START, datetime.min.time()) + timedelta(
            days=int(key_day[k]), seconds=int(key_second[k])
        )
        pid = int(key_product[k])
        rows.append({
            "product_id": pid,
            "seller_id": int(key_seller[k]),
            "scraped_at": scraped,
            "category": CATEGORIES[pid % len(CATEGORIES)],
            "currency": CURRENCIES[int(currency_idx[i])],
            "price": float(price[i]),
            "in_stock": bool(in_stock[i]),
            "version": int(version[i]),
            "ingested_at": base_ingest + timedelta(seconds=int(version[i])),
        })
    rows.sort(key=lambda r: r["ingested_at"])
    return rows


if __name__ == "__main__":
    sys.exit(generate())
