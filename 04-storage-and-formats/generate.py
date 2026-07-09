"""Deterministic generator of scraped price-snapshot data for module 04.

Writes JSONL chunks to data/raw/ and ground-truth aggregates to
data/ground-truth.json. Streaming: memory stays bounded regardless of
target size. Fixed seeds: rerunning with the same arguments reproduces
byte-identical output.

Usage:
    uv run python generate.py --gb 5
    uv run python generate.py --gb 0.2
    uv run python generate.py --rows 1000000
"""

import argparse
import calendar
import json
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from faker import Faker

SEED = 40404
MODULE_ROOT = Path(__file__).resolve().parent
RAW_DIR = MODULE_ROOT / "data" / "raw"
GROUND_TRUTH_PATH = MODULE_ROOT / "data" / "ground-truth.json"

N_PRODUCTS = 200_000
N_SOURCES = 40
CHUNK_ROWS = 200_000
ROWS_PER_FILE = 1_000_000

# 18 months: 2025-01-01 .. 2026-06-30 (inclusive)
START = datetime(2025, 1, 1, tzinfo=timezone.utc)
MONTHS = [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 7)]
MONTH_KEYS = [f"{y:04d}-{m:02d}" for y, m in MONTHS]
DAYS_IN_MONTH = [calendar.monthrange(y, m)[1] for y, m in MONTHS]
MONTH_STARTS = []
for y, m in MONTHS:
    MONTH_STARTS.append(int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp()))

CURRENCIES = ["USD", "EUR", "GBP", "PLN"]
# each source scrapes one marketplace, hence one currency
SOURCE_CURRENCY_IDX = None  # filled in setup

FILTER_PROBE_SOURCE = 3
FILTER_PROBE_FROM = "2025-09-01"
FILTER_PROBE_TO = "2025-10-31"  # inclusive
LATEST_PROBE_RANKS = [0, 1, 2, 5, 10, 20, 50, 100, 500, 1000]  # hot products, present at any size

CATEGORY_ROOTS = [
    "electronics", "home-appliances", "kitchen", "toys", "sporting-goods",
    "office-supplies", "beauty", "grocery", "pet-supplies", "tools",
    "furniture", "footwear", "apparel", "books", "garden",
]

ATTR_KEYS = [
    ("color", "word"), ("material", "word"), ("weight_g", "int"),
    ("width_mm", "int"), ("height_mm", "int"), ("depth_mm", "int"),
    ("rating", "float"), ("review_count", "int"), ("warranty_months", "int"),
    ("country_of_origin", "cc"), ("ean", "digits"), ("model_year", "year"),
    ("energy_class", "letter"), ("tags", "words"), ("in_original_box", "bool"),
    ("refurbished", "bool"), ("seller_rank", "int"), ("shipping_days", "int"),
    ("bundle_size", "int"), ("limited_edition", "bool"),
]

UNICODE_DECOR = ["", "", "", " ™", " ®", " – Original",
                 " ★", " セール", " СКИДКА",
                 " édition spéciale", " größe XL", ""]


def build_universe(rng, fake):
    """Pre-generate the product universe; per-row generation only samples it."""
    roots = rng.integers(0, len(CATEGORY_ROOTS), size=300)
    cat_paths = []
    for i in range(300):
        mid = fake.word()
        leaf = fake.word()
        cat_paths.append(f"{CATEGORY_ROOTS[roots[i]]}/{mid}/{leaf}")

    brands = [fake.company().replace('"', "") for _ in range(120)]

    prod_cat_idx = rng.integers(0, 300, size=N_PRODUCTS)
    prod_brand_idx = rng.integers(0, 120, size=N_PRODUCTS)
    prod_base_price = np.round(np.exp(rng.normal(3.3, 1.1, size=N_PRODUCTS)) + 0.99, 2)
    prod_base_price = np.clip(prod_base_price, 0.99, 25000.0)

    word_pool = [fake.word() for _ in range(800)]
    decor_idx = rng.integers(0, len(UNICODE_DECOR), size=N_PRODUCTS)
    nwords = rng.integers(2, 6, size=N_PRODUCTS)
    word_idx = rng.integers(0, 800, size=(N_PRODUCTS, 5))
    model_no = rng.integers(100, 99999, size=N_PRODUCTS)

    titles_json = []
    for i in range(N_PRODUCTS):
        words = " ".join(word_pool[j] for j in word_idx[i, : nwords[i]])
        title = f"{brands[prod_brand_idx[i]]} {words.title()} {model_no[i]}{UNICODE_DECOR[decor_idx[i]]}"
        titles_json.append(json.dumps(title, ensure_ascii=False))

    n_attrs = rng.integers(5, 14, size=N_PRODUCTS)
    key_order = np.argsort(rng.random((N_PRODUCTS, len(ATTR_KEYS))), axis=1)
    cc_pool = ["CN", "DE", "US", "PL", "VN", "TR", "IT", "KR"]
    attrs_json = []
    for i in range(N_PRODUCTS):
        parts = []
        for k in key_order[i, : n_attrs[i]]:
            name, kind = ATTR_KEYS[k]
            if kind == "word":
                v = json.dumps(word_pool[int(rng.integers(0, 800))])
            elif kind == "int":
                v = str(int(rng.integers(1, 5000)))
            elif kind == "float":
                v = f"{rng.uniform(1.0, 5.0):.2f}"
            elif kind == "cc":
                v = json.dumps(cc_pool[int(rng.integers(0, len(cc_pool)))])
            elif kind == "digits":
                v = json.dumps(str(int(rng.integers(10**12, 10**13))))
            elif kind == "year":
                v = str(int(rng.integers(2015, 2027)))
            elif kind == "letter":
                v = json.dumps("ABCDEFG"[int(rng.integers(0, 7))])
            elif kind == "words":
                ws = [word_pool[int(j)] for j in rng.integers(0, 800, size=3)]
                v = json.dumps(ws)
            else:
                v = "true" if rng.random() < 0.5 else "false"
            parts.append(f'"{name}":{v}')
        attrs_json.append("{" + ",".join(parts))  # closed per-row with 2 extra keys

    src_domains = [fake.domain_name() for _ in range(N_SOURCES)]
    src_currency = rng.integers(0, len(CURRENCIES), size=N_SOURCES)

    cats_json = [json.dumps(c) for c in cat_paths]
    brands_json = [json.dumps(b, ensure_ascii=False) for b in brands]

    return {
        "prod_cat_idx": prod_cat_idx,
        "prod_brand_idx": prod_brand_idx,
        "prod_base_price": prod_base_price,
        "titles_json": titles_json,
        "attrs_json": attrs_json,
        "cats_json": cats_json,
        "brands_json": brands_json,
        "src_domains": src_domains,
        "src_currency": src_currency,
    }


def month_weights():
    w = np.ones(len(MONTHS))
    for i, (y, m) in enumerate(MONTHS):
        if m == 11:
            w[i] = 1.8
        elif m == 12:
            w[i] = 1.6
        elif m in (1, 2):
            w[i] = 0.8
    return w / w.sum()


def hour_weights():
    h = np.arange(24)
    w = 0.3 + np.exp(-((h - 14) ** 2) / 40.0)
    return w / w.sum()


class GroundTruth:
    def __init__(self, probe_products):
        self.probe_products = probe_products
        self.total_rows = 0
        self.currency_counts = {c: 0 for c in CURRENCIES}
        self.rows_by_month = {k: 0 for k in MONTH_KEYS}
        self.price_sum_by_month = {k: 0.0 for k in MONTH_KEYS}
        self.distinct = np.zeros(N_PRODUCTS + 1, dtype=bool)
        self.probe_rows = 0
        self.probe_price_sum = 0.0
        self.latest = {p: (-1, None) for p in probe_products}

    def update(self, product_id, source_id, cur_idx, month_idx, ts, price, ok_mask):
        n = len(product_id)
        self.total_rows += n
        cc = np.bincount(cur_idx, minlength=len(CURRENCIES))
        for i, c in enumerate(CURRENCIES):
            self.currency_counts[c] += int(cc[i])
        mc = np.bincount(month_idx, minlength=len(MONTHS))
        ps = np.bincount(month_idx[ok_mask], weights=price[ok_mask], minlength=len(MONTHS))
        for i, k in enumerate(MONTH_KEYS):
            self.rows_by_month[k] += int(mc[i])
            self.price_sum_by_month[k] += float(ps[i])
        self.distinct[np.unique(product_id)] = True

        pf = int(datetime.strptime(FILTER_PROBE_FROM, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        pt = int((datetime.strptime(FILTER_PROBE_TO, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)).timestamp())
        probe = (source_id == FILTER_PROBE_SOURCE) & (ts >= pf) & (ts < pt)
        self.probe_rows += int(probe.sum())
        self.probe_price_sum += float(price[probe & ok_mask].sum())

        for p in self.probe_products:
            m = (product_id == p) & ok_mask
            if m.any():
                idx = np.nonzero(m)[0]
                best = idx[np.argmax(ts[idx])]
                if int(ts[best]) > self.latest[p][0]:
                    self.latest[p] = (int(ts[best]), round(float(price[best]), 2))

    def dump(self):
        return {
            "total_rows": self.total_rows,
            "distinct_products": int(self.distinct.sum()),
            "currency_counts": self.currency_counts,
            "rows_by_month": self.rows_by_month,
            "price_sum_by_month": {k: round(v, 2) for k, v in self.price_sum_by_month.items()},
            "filter_probe": {
                "source_id": FILTER_PROBE_SOURCE,
                "captured_at_from": FILTER_PROBE_FROM,
                "captured_at_to": FILTER_PROBE_TO,
                "rows": self.probe_rows,
                "price_sum": round(self.probe_price_sum, 2),
            },
            "latest_price_probe": {
                str(p): {"captured_at_epoch": t, "price": pr}
                for p, (t, pr) in self.latest.items() if t >= 0
            },
        }


def generate(target_bytes, target_rows):
    rng = np.random.default_rng(SEED)
    fake = Faker()
    Faker.seed(SEED)

    print("building product universe (200k products, 40 sources)...")
    t0 = time.time()
    u = build_universe(rng, fake)
    print(f"universe ready in {time.time() - t0:.1f}s")

    if RAW_DIR.exists():
        shutil.rmtree(RAW_DIR)
    RAW_DIR.mkdir(parents=True)

    mw = month_weights()
    hw = hour_weights()

    perm = rng.permutation(N_PRODUCTS) + 1  # zipf rank -> product_id
    src_perm = rng.permutation(N_SOURCES) + 1
    gt = GroundTruth([int(perm[r]) for r in LATEST_PROBE_RANKS])

    bytes_written = 0
    rows_written = 0
    file_idx = 0
    rows_in_file = 0
    fh = None
    t_start = time.time()

    def open_next():
        nonlocal file_idx, rows_in_file, fh
        if fh:
            fh.close()
        fh = open(RAW_DIR / f"part-{file_idx:04d}.jsonl", "w", encoding="utf-8", newline="\n")
        file_idx += 1
        rows_in_file = 0

    open_next()

    while True:
        if target_rows is not None:
            remaining = target_rows - rows_written
            if remaining <= 0:
                break
            n = min(CHUNK_ROWS, remaining)
        else:
            if bytes_written >= target_bytes:
                break
            n = CHUNK_ROWS

        rank = rng.zipf(1.25, size=n)
        rank = np.clip(rank, 1, N_PRODUCTS) - 1
        product_id = perm[rank]

        srank = rng.zipf(1.4, size=n)
        srank = np.clip(srank, 1, N_SOURCES) - 1
        source_id = src_perm[srank]

        month_idx = rng.choice(len(MONTHS), size=n, p=mw)
        day = (rng.random(n) * np.array(DAYS_IN_MONTH)[month_idx]).astype(np.int64)
        hour = rng.choice(24, size=n, p=hw)
        sec_of_day = hour * 3600 + rng.integers(0, 3600, size=n)
        ts = np.array(MONTH_STARTS)[month_idx] + day * 86400 + sec_of_day

        base = u["prod_base_price"][product_id - 1]
        noise = np.exp(rng.normal(0, 0.12, size=n))
        seasonal = np.where(np.isin(month_idx, [10, 11]), 0.92, 1.0)
        price = np.round(base * noise * seasonal, 2)

        http_roll = rng.random(n)
        status = np.full(n, 200, dtype=np.int64)
        status[http_roll > 0.985] = 404
        status[http_roll > 0.997] = 503
        ok_mask = status == 200

        in_stock = rng.random(n) < 0.85
        cur_idx = u["src_currency"][source_id - 1]

        run_date = ts - (ts % 86400)

        lines = []
        titles = u["titles_json"]
        attrs = u["attrs_json"]
        cats = u["cats_json"]
        brands = u["brands_json"]
        pos = rng.integers(1, 400, size=n)
        for i in range(n):
            p = int(product_id[i])
            s = int(source_id[i])
            st = int(status[i])
            iso = datetime.fromtimestamp(int(ts[i]), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            rd = datetime.fromtimestamp(int(run_date[i]), tz=timezone.utc).strftime("%Y%m%d")
            if st == 200:
                price_s = f"{price[i]:.2f}"
                stock_s = "true" if in_stock[i] else "false"
            else:
                price_s = "null"
                stock_s = "null"
            lines.append(
                '{"product_id":%d,"source_id":%d,'
                '"url":"https://%s/p/%d?ref=pw","title":%s,'
                '"category":%s,"brand":%s,'
                '"price":%s,"currency":"%s","in_stock":%s,'
                '"captured_at":"%s",'
                '"attrs":%s,"page_position":%d,"badge":%s},'
                '"scrape_run_id":"run-%s-%02d","http_status":%d}'
                % (
                    p, s,
                    u["src_domains"][s - 1], p, titles[p - 1],
                    cats[u["prod_cat_idx"][p - 1]], brands[u["prod_brand_idx"][p - 1]],
                    price_s, CURRENCIES[cur_idx[i]], stock_s,
                    iso,
                    attrs[p - 1], int(pos[i]),
                    '"sponsored"' if (i % 17 == 0) else "null",
                    rd, s, st,
                )
            )
        blob = "\n".join(lines) + "\n"
        fh.write(blob)
        bytes_written += len(blob.encode("utf-8"))
        rows_written += n
        rows_in_file += n

        gt.update(product_id, source_id, cur_idx, month_idx, ts, price, ok_mask)

        if rows_in_file >= ROWS_PER_FILE:
            open_next()

        elapsed = time.time() - t_start
        print(f"  {rows_written:,} rows, {bytes_written / 1e9:.2f} GB, {elapsed:.0f}s", flush=True)

    if fh:
        fh.close()
    last = RAW_DIR / f"part-{file_idx - 1:04d}.jsonl"
    if last.exists() and last.stat().st_size == 0:
        last.unlink()

    GROUND_TRUTH_PATH.write_text(json.dumps(gt.dump(), indent=2), encoding="utf-8")
    print(f"done: {rows_written:,} rows, {bytes_written / 1e9:.2f} GB in {time.time() - t_start:.0f}s")
    print(f"raw JSONL: {RAW_DIR}")
    print(f"ground truth: {GROUND_TRUTH_PATH}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gb", type=float, default=5.0, help="target size in GB (default 5)")
    ap.add_argument("--rows", type=int, default=None, help="exact row count (overrides --gb)")
    args = ap.parse_args()
    if args.rows is not None:
        generate(None, args.rows)
    else:
        generate(int(args.gb * 1e9), None)


if __name__ == "__main__":
    sys.exit(main())
