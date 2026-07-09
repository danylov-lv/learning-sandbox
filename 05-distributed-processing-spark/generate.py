"""Deterministic generator of scraped price-event data for module 05.

Continues the PriceWatch universe from module 04, scaled up and made
messier for distributed-processing tasks: retry-storm duplicates, a
skewed source distribution (one source ~30% of all rows), a small
fraction of malformed (unparseable) JSON lines, and nested attrs.

Writes:
- data/raw-events/part-*.jsonl  — raw scrape dumps (messy, as scraped)
- data/reference/sources.csv    — ~20 source rows for join tasks
- data/reference/categories.csv — a few hundred category rows for join tasks
- data/ground-truth.json        — aggregates computed during generation

Streaming: memory stays bounded regardless of target size. Fixed seeds:
rerunning with the same arguments reproduces byte-identical output.

Usage:
    uv run python generate.py --rows 50000000    # default-scale run
    uv run python generate.py --rows 2000000      # authoring test set
    uv run python generate.py --gb 10
"""

import argparse
import calendar
import csv
import json
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from faker import Faker

SEED = 50505
MODULE_ROOT = Path(__file__).resolve().parent
RAW_DIR = MODULE_ROOT / "data" / "raw-events"
REFERENCE_DIR = MODULE_ROOT / "data" / "reference"
GROUND_TRUTH_PATH = MODULE_ROOT / "data" / "ground-truth.json"

N_PRODUCTS = 300_000
N_SOURCES = 20
N_CATEGORIES = 240
CHUNK_ROWS = 200_000
ROWS_PER_FILE = 2_000_000

DUP_RATE = 0.03          # retry-storm duplicates, ~2-4% of valid rows
MALFORMED_RATE = 0.0015  # unparseable lines, on top of valid rows

# 18 months: 2025-01-01 .. 2026-06-30 (inclusive) — same window as module 04
MONTHS = [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 7)]
MONTH_KEYS = [f"{y:04d}-{m:02d}" for y, m in MONTHS]
DAYS_IN_MONTH = [calendar.monthrange(y, m)[1] for y, m in MONTHS]
MONTH_STARTS = [int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp()) for y, m in MONTHS]

CURRENCIES = ["USD", "EUR", "GBP", "PLN"]

FILTER_PROBE_SOURCE = 4
FILTER_PROBE_FROM = "2025-09-01"
FILTER_PROBE_TO = "2025-10-31"  # inclusive
TOP_N_PER_SOURCE = 3  # for window-function ranking tasks

REGIONS = ["us", "eu", "uk", "apac"]
TIERS = ["tier1", "tier2", "tier3"]

ATTR_KEYS = [
    ("color", "word"), ("material", "word"), ("weight_g", "int"),
    ("width_mm", "int"), ("height_mm", "int"), ("rating", "float"),
    ("review_count", "int"), ("warranty_months", "int"),
    ("country_of_origin", "cc"), ("model_year", "year"),
    ("energy_class", "letter"), ("in_original_box", "bool"),
    ("refurbished", "bool"), ("shipping_days", "int"),
]

UNICODE_DECOR = ["", "", "", " ™", " ®", " – Original",
                 " ★", " セール", " СКИДКА", " édition spéciale", ""]


def build_universe(rng, fake):
    """Pre-generate the product/source/category universe."""
    cat_ids = list(range(N_CATEGORIES))
    cat_paths = []
    verticals = ["electronics", "home", "kitchen", "toys", "sport", "office",
                 "beauty", "grocery", "pets", "tools", "furniture", "apparel"]
    vert_idx = rng.integers(0, len(verticals), size=N_CATEGORIES)
    for i in cat_ids:
        mid = fake.word()
        leaf = fake.word()
        cat_paths.append(f"{verticals[vert_idx[i]]}/{mid}/{leaf}")

    brands = [fake.company().replace('"', "") for _ in range(150)]

    prod_cat_idx = rng.integers(0, N_CATEGORIES, size=N_PRODUCTS)
    prod_brand_idx = rng.integers(0, 150, size=N_PRODUCTS)
    prod_base_price = np.round(np.exp(rng.normal(3.3, 1.1, size=N_PRODUCTS)) + 0.99, 2)
    prod_base_price = np.clip(prod_base_price, 0.99, 25000.0)

    word_pool = [fake.word() for _ in range(600)]
    decor_idx = rng.integers(0, len(UNICODE_DECOR), size=N_PRODUCTS)
    nwords = rng.integers(2, 6, size=N_PRODUCTS)
    word_idx = rng.integers(0, 600, size=(N_PRODUCTS, 5))
    model_no = rng.integers(100, 99999, size=N_PRODUCTS)

    titles_json = []
    for i in range(N_PRODUCTS):
        words = " ".join(word_pool[j] for j in word_idx[i, : nwords[i]])
        title = f"{brands[prod_brand_idx[i]]} {words.title()} {model_no[i]}{UNICODE_DECOR[decor_idx[i]]}"
        titles_json.append(json.dumps(title, ensure_ascii=False))

    n_attrs = rng.integers(4, len(ATTR_KEYS), size=N_PRODUCTS)
    key_order = np.argsort(rng.random((N_PRODUCTS, len(ATTR_KEYS))), axis=1)
    cc_pool = ["CN", "DE", "US", "PL", "VN", "TR", "IT", "KR"]
    attrs_json = []
    for i in range(N_PRODUCTS):
        parts = []
        for k in key_order[i, : n_attrs[i]]:
            name, kind = ATTR_KEYS[k]
            if kind == "word":
                v = json.dumps(word_pool[int(rng.integers(0, 600))])
            elif kind == "int":
                v = str(int(rng.integers(1, 5000)))
            elif kind == "float":
                v = f"{rng.uniform(1.0, 5.0):.2f}"
            elif kind == "cc":
                v = json.dumps(cc_pool[int(rng.integers(0, len(cc_pool)))])
            elif kind == "year":
                v = str(int(rng.integers(2015, 2027)))
            elif kind == "letter":
                v = json.dumps("ABCDEFG"[int(rng.integers(0, 7))])
            else:
                v = "true" if rng.random() < 0.5 else "false"
            parts.append(f'"{name}":{v}')
        attrs_json.append("{" + ",".join(parts) + "}")

    src_domains = [fake.domain_name() for _ in range(N_SOURCES)]
    src_names = [fake.company().replace('"', "") for _ in range(N_SOURCES)]
    src_currency = rng.integers(0, len(CURRENCIES), size=N_SOURCES)
    src_region = rng.integers(0, len(REGIONS), size=N_SOURCES)
    src_tier = rng.integers(0, len(TIERS), size=N_SOURCES)

    return {
        "cat_paths": cat_paths,
        "vert_idx": vert_idx,
        "prod_cat_idx": prod_cat_idx,
        "prod_brand_idx": prod_brand_idx,
        "prod_base_price": prod_base_price,
        "titles_json": titles_json,
        "attrs_json": attrs_json,
        "brands": brands,
        "src_domains": src_domains,
        "src_names": src_names,
        "src_currency": src_currency,
        "src_region": src_region,
        "src_tier": src_tier,
    }


def write_reference_tables(u):
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    with open(REFERENCE_DIR / "sources.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_id", "domain", "name", "region", "default_currency", "tier"])
        for s in range(N_SOURCES):
            w.writerow([
                s + 1, u["src_domains"][s], u["src_names"][s],
                REGIONS[u["src_region"][s]], CURRENCIES[u["src_currency"][s]],
                TIERS[u["src_tier"][s]],
            ])
    with open(REFERENCE_DIR / "categories.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category_id", "category_path", "vertical"])
        verticals = ["electronics", "home", "kitchen", "toys", "sport", "office",
                     "beauty", "grocery", "pets", "tools", "furniture", "apparel"]
        for i, path in enumerate(u["cat_paths"]):
            w.writerow([i + 1, path, verticals[u["vert_idx"][i]]])


def source_weights():
    """One source dominant at 30%, the rest zipf-ish over the remaining 70%."""
    w = np.zeros(N_SOURCES)
    w[0] = 0.30
    rest = np.array([1.0 / (i ** 1.3) for i in range(1, N_SOURCES)])
    w[1:] = rest / rest.sum() * 0.70
    return w


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
    def __init__(self):
        self.total_rows_raw = 0       # all valid-JSON lines, including duplicates
        self.exact_dupe_count = 0
        self.malformed_line_count = 0
        self.rows_by_source = {str(s + 1): 0 for s in range(N_SOURCES)}
        self.rows_by_month = {k: 0 for k in MONTH_KEYS}
        self.price_sum_by_month = {k: 0.0 for k in MONTH_KEYS}
        self.probe_rows = 0
        self.probe_price_sum = 0.0
        # top-N-per-source, by price, over deduped status==200 rows
        self._top = {s + 1: [] for s in range(N_SOURCES)}

    def update_dedup(self, product_id, source_id, month_idx, ts, price, ok_mask):
        n = len(product_id)
        sc = np.bincount(source_id, minlength=N_SOURCES + 1)
        for s in range(N_SOURCES):
            self.rows_by_source[str(s + 1)] += int(sc[s + 1])
        mc = np.bincount(month_idx, minlength=len(MONTHS))
        ps = np.bincount(month_idx[ok_mask], weights=price[ok_mask], minlength=len(MONTHS))
        for i, k in enumerate(MONTH_KEYS):
            self.rows_by_month[k] += int(mc[i])
            self.price_sum_by_month[k] += float(ps[i])

        pf = int(datetime.strptime(FILTER_PROBE_FROM, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        pt = int((datetime.strptime(FILTER_PROBE_TO, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)).timestamp())
        probe = (source_id == FILTER_PROBE_SOURCE) & (ts >= pf) & (ts < pt)
        self.probe_rows += int(probe.sum())
        self.probe_price_sum += float(price[probe & ok_mask].sum())

        idxs = np.nonzero(ok_mask)[0]
        for i in idxs:
            s = int(source_id[i])
            heap = self._top[s]
            entry = (float(price[i]), int(product_id[i]))
            heap.append(entry)
            if len(heap) > 200:
                heap.sort(reverse=True)
                del heap[TOP_N_PER_SOURCE * 4:]

    def finalize_top(self):
        out = {}
        for s in range(1, N_SOURCES + 1):
            heap = sorted(self._top[s], reverse=True)[:TOP_N_PER_SOURCE]
            out[str(s)] = [{"price": round(p, 2), "product_id": pid} for p, pid in heap]
        return out

    def dump(self):
        return {
            "total_rows_raw": self.total_rows_raw,
            "exact_dupe_count": self.exact_dupe_count,
            "distinct_rows": self.total_rows_raw - self.exact_dupe_count,
            "malformed_line_count": self.malformed_line_count,
            "rows_by_source": self.rows_by_source,
            "rows_by_month": self.rows_by_month,
            "price_sum_by_month": {k: round(v, 2) for k, v in self.price_sum_by_month.items()},
            "filter_probe": {
                "source_id": FILTER_PROBE_SOURCE,
                "captured_at_from": FILTER_PROBE_FROM,
                "captured_at_to": FILTER_PROBE_TO,
                "rows": self.probe_rows,
                "price_sum": round(self.probe_price_sum, 2),
            },
            "top_n_per_source": {
                "n": TOP_N_PER_SOURCE,
                "note": "top prices per source_id, deduped, http_status==200 rows only, ties broken by price desc then product_id desc",
                "by_source": self.finalize_top(),
            },
        }


def generate(target_bytes, target_rows):
    rng = np.random.default_rng(SEED)
    fake = Faker()
    Faker.seed(SEED)

    print("building product/source/category universe...")
    t0 = time.time()
    u = build_universe(rng, fake)
    write_reference_tables(u)
    print(f"universe + reference tables ready in {time.time() - t0:.1f}s")

    if RAW_DIR.exists():
        shutil.rmtree(RAW_DIR)
    RAW_DIR.mkdir(parents=True)

    mw = month_weights()
    hw = hour_weights()
    sw = source_weights()

    perm = rng.permutation(N_PRODUCTS) + 1  # rank -> product_id

    gt = GroundTruth()

    bytes_written = 0
    rows_written = 0  # valid rows only (raw, including dupes), target metric
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

        rank = rng.zipf(1.2, size=n)
        rank = np.clip(rank, 1, N_PRODUCTS) - 1
        product_id = perm[rank]

        source_id = rng.choice(np.arange(1, N_SOURCES + 1), size=n, p=sw)

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
        status[http_roll > 0.98] = 404
        status[http_roll > 0.996] = 503
        ok_mask = status == 200

        in_stock = rng.random(n) < 0.85
        cur_idx = u["src_currency"][source_id - 1]
        run_date = ts - (ts % 86400)

        titles = u["titles_json"]
        attrs = u["attrs_json"]
        cat_idx = u["prod_cat_idx"]
        brand_idx = u["prod_brand_idx"]
        pos = rng.integers(1, 400, size=n)

        lines = []
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
                '"category_id":%d,'
                '"price":%s,"currency":"%s","in_stock":%s,'
                '"captured_at":"%s",'
                '"attrs":%s,"page_position":%d,'
                '"scrape_run_id":"run-%s-%02d","http_status":%d}'
                % (
                    p, s,
                    u["src_domains"][s - 1], p, titles[p - 1],
                    cat_idx[p - 1] + 1,
                    price_s, CURRENCIES[cur_idx[i]], stock_s,
                    iso,
                    attrs[p - 1], int(pos[i]),
                    rd, s, st,
                )
            )

        # retry-storm duplicates: repeat some already-built lines verbatim
        n_dupe = int(round(n * DUP_RATE))
        if n_dupe > 0:
            dupe_src_idx = rng.integers(0, n, size=n_dupe)
            dupe_lines = [lines[i] for i in dupe_src_idx]
            insert_at = rng.integers(0, len(lines) + 1, size=n_dupe)
            order = np.argsort(-insert_at)  # insert back-to-front so indices stay valid
            for k in order:
                lines.insert(int(insert_at[k]), dupe_lines[k])
            gt.exact_dupe_count += n_dupe

        # malformed lines: unparseable garbage injected on top of the valid stream
        n_malformed = int(round(n * MALFORMED_RATE))
        if n_malformed > 0:
            for _ in range(n_malformed):
                where = int(rng.integers(0, len(lines) + 1))
                bad_kind = int(rng.integers(0, 3))
                if bad_kind == 0:
                    garbage = lines[min(where, len(lines) - 1)][: rng.integers(10, 60)] if lines else "{broken"
                elif bad_kind == 1:
                    garbage = "{\"product_id\": " + str(int(rng.integers(1, N_PRODUCTS))) + ", truncated"
                else:
                    garbage = "NOT_JSON " + fake.sentence()
                lines.insert(where, garbage)
            gt.malformed_line_count += n_malformed

        blob = "\n".join(lines) + "\n"
        fh.write(blob)
        bytes_written += len(blob.encode("utf-8"))
        rows_written += n  # count only the valid canonical rows toward the target
        gt.total_rows_raw += n + n_dupe
        rows_in_file += n + n_dupe + n_malformed

        gt.update_dedup(product_id, source_id, month_idx, ts, price, ok_mask)

        if rows_in_file >= ROWS_PER_FILE:
            open_next()

        elapsed = time.time() - t_start
        print(f"  {rows_written:,} valid rows, {bytes_written / 1e9:.2f} GB, {elapsed:.0f}s", flush=True)

    if fh:
        fh.close()
    last = RAW_DIR / f"part-{file_idx - 1:04d}.jsonl"
    if last.exists() and last.stat().st_size == 0:
        last.unlink()

    GROUND_TRUTH_PATH.write_text(json.dumps(gt.dump(), indent=2), encoding="utf-8")
    print(f"done: {rows_written:,} valid rows written ({gt.total_rows_raw:,} raw incl. dupes, "
          f"{gt.malformed_line_count:,} malformed), {bytes_written / 1e9:.2f} GB in {time.time() - t_start:.0f}s")
    print(f"raw JSONL: {RAW_DIR}")
    print(f"reference tables: {REFERENCE_DIR}")
    print(f"ground truth: {GROUND_TRUTH_PATH}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gb", type=float, default=None, help="target size in GB")
    ap.add_argument("--rows", type=int, default=50_000_000, help="exact valid-row count (default 50,000,000)")
    args = ap.parse_args()
    if args.gb is not None:
        generate(int(args.gb * 1e9), None)
    else:
        generate(None, args.rows)


if __name__ == "__main__":
    sys.exit(main())
