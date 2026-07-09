"""Deterministic seed generator for the price-intelligence snapshot warehouse.

Writes CSVs to data/ (vectorized numpy), then bulk-loads them into Postgres
via COPY. Fixed seeds: the same --scale always produces identical data.
"""

import argparse
import csv
import functools
import os
import sys
import time
from pathlib import Path

import numpy as np
import psycopg
from faker import Faker

SEED = 20260701
START = np.datetime64("2025-01-01")  # span: 2025-01-01 .. 2026-06-30 (18 months)
N_DAYS = 546

N_SOURCES = 300
N_BRANDS = 80
BASE_PRODUCTS = 200_000
BASE_SNAPSHOTS = 4_000_000

CURRENCIES = ["USD", "EUR", "GBP", "PLN"]
CUR_START_RATE = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "PLN": 0.25}
COUNTRY_POOL = [
    ("US", "USD", 0.26), ("CA", "USD", 0.06), ("GB", "GBP", 0.12),
    ("DE", "EUR", 0.12), ("FR", "EUR", 0.09), ("PL", "PLN", 0.09),
    ("ES", "EUR", 0.07), ("IT", "EUR", 0.07), ("NL", "EUR", 0.06),
    ("IE", "EUR", 0.06),
]
ROOT_CATEGORIES = [
    "Electronics", "Home & Garden", "Sports & Outdoors", "Toys & Hobbies",
    "Automotive", "Health & Beauty", "Fashion", "Pet Supplies",
]
PRODUCT_NOUNS = [
    "Charger", "Headset", "Blender", "Kettle", "Drill", "Lamp", "Backpack",
    "Monitor", "Keyboard", "Router", "Speaker", "Tent", "Helmet", "Jacket",
    "Sneakers", "Watch", "Tripod", "Cable", "Mixer", "Heater", "Fan",
    "Scooter", "Cam", "Sensor", "Hub", "Mat", "Bottle", "Case", "Stand",
    "Vacuum", "Purifier", "Grinder", "Toaster", "Projector", "Mouse",
    "Adapter", "Battery", "Filter", "Pump", "Rack", "Stroller", "Scale",
    "Thermostat", "Doorbell", "Lock", "Frame", "Desk", "Chair", "Shelf",
    "Cooler",
]

MODULE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = MODULE_DIR / "data"


def db_connect():
    return psycopg.connect(
        host=os.environ.get("SANDBOX_01_HOST", "localhost"),
        port=int(os.environ.get("SANDBOX_01_PORT", "54301")),
        dbname="sandbox",
        user="sandbox",
        password="sandbox",
    )


def weighted_sample(rng, weights, n):
    cum = np.cumsum(weights)
    return np.searchsorted(cum, rng.random(n) * cum[-1], side="right").astype(np.int64)


def gen_sources(rng, fake):
    countries, currencies = [], []
    probs = np.array([c[2] for c in COUNTRY_POOL])
    idx = weighted_sample(rng, probs, N_SOURCES)
    for i in idx:
        countries.append(COUNTRY_POOL[i][0])
        currencies.append(COUNTRY_POOL[i][1])
    tiers = rng.choice([1, 2, 3], size=N_SOURCES, p=[0.08, 0.30, 0.62])
    names = [fake.unique.company() for _ in range(N_SOURCES)]
    return names, countries, np.array(tiers), currencies


def gen_categories(rng, fake):
    # rows: (id, name, parent_id or None, level)
    rows = []
    next_id = 1
    words = [w.capitalize() for w in fake.words(nb=300, unique=True)]
    rng.shuffle(words)
    widx = 0

    def next_word():
        nonlocal widx
        w = words[widx % len(words)]
        widx += 1
        return w

    roots = []
    for name in ROOT_CATEGORIES:
        rows.append((next_id, name, None, 0))
        roots.append(next_id)
        next_id += 1
    level1 = []
    for r in roots:
        for _ in range(5):
            rows.append((next_id, f"{next_word()} {next_word()}", r, 1))
            level1.append(next_id)
            next_id += 1
    level2 = []
    for c1 in level1:
        for _ in range(int(rng.integers(3, 5))):
            rows.append((next_id, f"{next_word()} {next_word()}", c1, 2))
            level2.append(next_id)
            next_id += 1
    leaves = []
    for c2 in level2:
        for _ in range(int(rng.integers(2, 4))):
            rows.append((next_id, f"{next_word()} {next_word()}", c2, 3))
            leaves.append(next_id)
            next_id += 1
    return rows, np.array(leaves)


def gen_exchange_rates(rng):
    rates = np.empty((len(CURRENCIES), N_DAYS))
    for i, cur in enumerate(CURRENCIES):
        if cur == "USD":
            rates[i, :] = 1.0
        else:
            walk = np.cumsum(rng.normal(0, 0.003, N_DAYS))
            rates[i, :] = CUR_START_RATE[cur] * np.exp(walk - walk[0])
    return rates


def gen_products(rng, fake, n_products, leaves):
    brands = [fake.unique.last_name() for _ in range(N_BRANDS)]
    leaf_w = (rng.pareto(1.2, len(leaves)) + 0.15)
    cat_idx = weighted_sample(rng, leaf_w, n_products)
    category_ids = leaves[cat_idx]
    brand_w = (np.arange(1, N_BRANDS + 1)) ** -0.7
    rng.shuffle(brand_w)
    brand_idx = weighted_sample(rng, brand_w, n_products)
    noun_idx = rng.integers(0, len(PRODUCT_NOUNS), n_products)
    model_a = rng.integers(65, 91, n_products)
    model_n = rng.integers(100, 9999, n_products)
    names = [
        f"{brands[b]} {PRODUCT_NOUNS[k]} {chr(a)}{m}"
        for b, k, a, m in zip(brand_idx, noun_idx, model_a, model_n)
    ]
    brand_names = [brands[b] for b in brand_idx]
    return names, category_ids, brand_names, cat_idx


def gen_snapshots(rng, n_products, n_snapshots, leaves, cat_idx, src_tiers, src_currency_idx, rates):
    P, N = n_products, n_snapshots

    # zipf-ish product popularity, decorrelated from product id
    pop = (np.arange(1, P + 1) + 30.0) ** -1.05
    rng.shuffle(pop)
    prod = weighted_sample(rng, pop, N)

    # source popularity by tier with jitter
    tier_w = np.where(src_tiers == 1, 30.0, np.where(src_tiers == 2, 6.0, 1.0))
    src_w = tier_w * rng.lognormal(0, 0.35, N_SOURCES)
    src = weighted_sample(rng, src_w, N)

    # day-of-span weights: yearly seasonality * day-of-week * growth trend
    days = np.arange(N_DAYS)
    doy = (days + 0) % 365
    seasonal = 1 + 0.25 * np.sin(2 * np.pi * (doy - 20) / 365.25)
    dow = (np.array([(int(d) + 2) % 7 for d in days]))  # 2025-01-01 is Wednesday
    dow_f = np.array([1.15, 1.15, 1.10, 1.10, 1.05, 0.72, 0.68])[dow]
    trend = np.linspace(0.8, 1.25, N_DAYS)
    day = weighted_sample(rng, seasonal * dow_f * trend, N).astype(np.int32)

    # hour-of-day profile: scraper waves at 02-05 and 14-17 UTC
    hour_w = np.array([3, 4, 8, 9, 8, 6, 3, 2, 2, 2, 3, 3, 3, 5, 8, 9, 8, 5, 3, 2, 1, 1, 1, 2], dtype=float)
    hour = weighted_sample(rng, hour_w, N).astype(np.int32)
    minute = rng.integers(0, 60, N, dtype=np.int32)
    second = rng.integers(0, 60, N, dtype=np.int32)

    ts = (
        START.astype("datetime64[s]")
        + (day.astype(np.int64) * 86400 + hour * 3600 + minute * 60 + second).astype("timedelta64[s]")
    )

    # prices: log-normal base per product, category-dependent location
    leaf_mu = np.clip(rng.normal(3.4, 0.9, len(leaves)), 1.5, 6.5)
    base_usd = np.exp(rng.normal(leaf_mu[cat_idx], 0.45))

    # persistent repricing events (drops and raises)
    event_day = np.full(P, N_DAYS + 1, dtype=np.int32)
    event_factor = np.ones(P)
    ev = rng.random(P)
    drop_m = ev < 0.05
    raise_m = (ev >= 0.05) & (ev < 0.08)
    event_day[drop_m | raise_m] = rng.integers(30, 516, int((drop_m | raise_m).sum()))
    event_factor[drop_m] = rng.uniform(0.55, 0.80, int(drop_m.sum()))
    event_factor[raise_m] = rng.uniform(1.15, 1.45, int(raise_m.sum()))

    phase = rng.uniform(0, 2 * np.pi, P)
    price_usd = (
        base_usd[prod]
        * (1 + 0.06 * np.sin(2 * np.pi * day / 365.25 + phase[prod]))
        * (1 + rng.normal(0, 0.02, N))
        * np.where(day >= event_day[prod], event_factor[prod], 1.0)
    )

    # transient per-snapshot spikes/drops (~0.7%)
    sp = rng.random(N)
    spike_lo = sp < 0.0035
    spike_hi = (sp >= 0.0035) & (sp < 0.007)
    price_usd[spike_lo] *= rng.uniform(0.40, 0.70, int(spike_lo.sum()))
    price_usd[spike_hi] *= rng.uniform(1.50, 2.20, int(spike_hi.sum()))
    price_usd = np.maximum(price_usd, 0.5)

    cur_idx = src_currency_idx[src]
    price_local = np.round(price_usd / rates[cur_idx, day], 2)

    # in-stock: up to 3 out-of-stock bursts per product + baseline noise (~2% total)
    out = np.zeros(N, dtype=bool)
    for _ in range(3):
        active = rng.random(P) < 0.5
        b_start = rng.integers(0, 541, P).astype(np.int32)
        b_len = rng.integers(1, 11, P).astype(np.int32)
        b_start[~active] = N_DAYS + 5
        out |= (day >= b_start[prod]) & (day < (b_start + b_len)[prod])
    out |= rng.random(N) < 0.006
    in_stock = ~out

    order = np.argsort(ts, kind="stable")
    return (
        prod[order], src[order], ts[order], price_local[order],
        cur_idx[order], in_stock[order], day[order],
    )


def write_snapshot_csv(path, prod, src, ts, price, cur_idx, in_stock):
    n = len(prod)
    parts = [
        np.arange(1, n + 1).astype("U9"),
        (prod + 1).astype("U9"),
        (src + 1).astype("U4"),
        np.datetime_as_string(ts, unit="s"),
        np.char.mod("%.2f", price),
        np.array(CURRENCIES, dtype="U3")[cur_idx],
        np.where(in_stock, "t", "f"),
    ]
    line = functools.reduce(lambda a, b: np.char.add(np.char.add(a, ","), b), parts)
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(line.tolist()))
        f.write("\n")


def copy_file(cur, table, path):
    with cur.copy(f"COPY {table} FROM STDIN (FORMAT csv)") as cp:
        with open(path, "rb") as f:
            while chunk := f.read(1 << 20):
                cp.write(chunk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0)
    args = ap.parse_args()

    t0 = time.time()
    rng = np.random.default_rng(SEED)
    Faker.seed(SEED)
    fake = Faker("en_US")
    DATA_DIR.mkdir(exist_ok=True)

    n_products = max(100, int(BASE_PRODUCTS * args.scale))
    n_snapshots = max(1000, int(BASE_SNAPSHOTS * args.scale))

    src_names, src_countries, src_tiers, src_currencies = gen_sources(rng, fake)
    src_currency_idx = np.array([CURRENCIES.index(c) for c in src_currencies])
    cat_rows, leaves = gen_categories(rng, fake)
    rates = gen_exchange_rates(rng)
    prod_names, prod_cat_ids, prod_brands, cat_idx = gen_products(rng, fake, n_products, leaves)

    prod, src, ts, price, cur_idx, in_stock, day = gen_snapshots(
        rng, n_products, n_snapshots, leaves, cat_idx, src_tiers, src_currency_idx, rates
    )

    # first_seen_at: min snapshot day minus 0-30 days; never-seen: random early date
    fs = np.full(n_products, 10 ** 9, dtype=np.int64)
    np.minimum.at(fs, prod, day.astype(np.int64))
    never = fs == 10 ** 9
    fs = np.maximum(fs - rng.integers(0, 31, n_products), 0)
    fs[never] = rng.integers(0, 180, int(never.sum()))
    first_seen = (START + fs.astype("timedelta64[D]")).astype("datetime64[D]")

    t1 = time.time()
    print(f"generated arrays in {t1 - t0:.1f}s")

    with open(DATA_DIR / "sources.csv", "w", newline="") as f:
        w = csv.writer(f)
        for i in range(N_SOURCES):
            w.writerow([i + 1, src_names[i], src_countries[i], int(src_tiers[i]), src_currencies[i]])
    with open(DATA_DIR / "categories.csv", "w", newline="") as f:
        w = csv.writer(f)
        for cid, name, parent, level in cat_rows:
            w.writerow([cid, name, "" if parent is None else parent, level])
    with open(DATA_DIR / "exchange_rates.csv", "w", newline="") as f:
        w = csv.writer(f)
        for i, cur in enumerate(CURRENCIES):
            for d in range(N_DAYS):
                w.writerow([cur, str(START + np.timedelta64(d, "D")), f"{rates[i, d]:.6f}"])
    with open(DATA_DIR / "products.csv", "w", newline="") as f:
        w = csv.writer(f)
        for i in range(n_products):
            w.writerow([i + 1, prod_names[i], int(prod_cat_ids[i]), prod_brands[i], str(first_seen[i])])
    write_snapshot_csv(DATA_DIR / "price_snapshots.csv", prod, src, ts, price, cur_idx, in_stock)

    t2 = time.time()
    print(f"wrote CSVs in {t2 - t1:.1f}s")

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute((MODULE_DIR / "seed" / "schema.sql").read_text())
            for table in ["sources", "categories", "products", "exchange_rates", "price_snapshots"]:
                copy_file(cur, table, DATA_DIR / f"{table}.csv")
            cur.execute((MODULE_DIR / "seed" / "post_load.sql").read_text())
        conn.commit()
        with conn.cursor() as cur:
            for table in ["sources", "categories", "products", "exchange_rates", "price_snapshots"]:
                cur.execute(f"SELECT count(*) FROM {table}")
                print(f"{table}: {cur.fetchone()[0]} rows")

    t3 = time.time()
    print(f"loaded into Postgres in {t3 - t2:.1f}s (total {t3 - t0:.1f}s)")


if __name__ == "__main__":
    sys.exit(main())
