"""Deterministic fixture generator for module t3 (CLI data toolkit).

Writes everything under data/ (gitignored, never committed). Re-running
this script produces byte-identical output -- a fixed seed drives every
random choice and nothing here reads wall-clock time.

Respects the SCALE env var (default 1.0) to grow/shrink record counts.
Total output stays a few MB even at SCALE=1.0 -- these are CLI drills,
not big-data.

Run from the module root:

    uv run python generate.py
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SEED = 20250713
MODULE_ROOT = Path(__file__).resolve().parent
DATA_DIR = MODULE_ROOT / "data"

SCALE = float(os.environ.get("SCALE", "1.0"))


def scaled(n: int) -> int:
    return max(1, round(n * SCALE))


CATEGORIES = ["electronics", "home", "beauty", "sports", "toys", "books"]
REGIONS = ["us-east", "us-west", "eu-west", "eu-central", "apac"]
SOURCES = [
    {"source_id": "s1", "source_name": "dealscout", "tier": "gold"},
    {"source_id": "s2", "source_name": "pricepatrol", "tier": "gold"},
    {"source_id": "s3", "source_name": "bargainbee", "tier": "silver"},
    {"source_id": "s4", "source_name": "clickwatch", "tier": "silver"},
    {"source_id": "s5", "source_name": "tinycrawl", "tier": "bronze"},
]

STATUS_POOL = [200, 200, 200, 201, 301, 304, 400, 404, 404, 429, 500, 502, 503, 504]
STATUS_WEIGHTS = np.array([14, 6, 4, 3, 3, 3, 4, 5, 3, 2, 3, 2, 2, 2], dtype=float)
STATUS_WEIGHTS /= STATUS_WEIGHTS.sum()


# --------------------------------------------------------------------------
# Task 01: nested scraped JSON catalog
# --------------------------------------------------------------------------

def gen_catalog(rng: np.random.Generator) -> None:
    out_dir = DATA_DIR / "scraped"
    out_dir.mkdir(parents=True, exist_ok=True)

    n_pages = scaled(24)
    pages = []
    product_counter = 0
    for page_num in range(1, n_pages + 1):
        source = SOURCES[int(rng.integers(0, len(SOURCES)))]
        n_listings = int(rng.integers(6, 15))
        listings = []
        for i in range(n_listings):
            product_counter += 1
            category = CATEGORIES[int(rng.integers(0, len(CATEGORIES)))]
            price_cents = int(np.clip(rng.lognormal(mean=3.4, sigma=0.6) * 1000, 499, 49999))
            listings.append(
                {
                    "listing_id": f"L{page_num:04d}-{i:02d}",
                    "product_id": f"P{product_counter:05d}",
                    "title": f"{category.capitalize()} item {product_counter}",
                    "category": category,
                    "price_cents": price_cents,
                    "currency": "USD",
                }
            )
        pages.append({"page_num": page_num, "source_id": source["source_id"], "listings": listings})

    catalog = {"scraped_at": "2026-07-01T00:00:00Z", "pages": pages}
    (out_dir / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    (out_dir / "sources.json").write_text(json.dumps(SOURCES, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# Task 02 (and 04): a varied file tree for rg / fd drills
# --------------------------------------------------------------------------

PY_TEMPLATES = [
    "def compute_price(base):\n    return round(base * 1.08, 2)\n",
    "# TODO: cache price lookups\nprice = fetch_price(sku)\n",
    "price_usd = normalize_currency(price, rate)\n",
    "class Listing:\n    def __init__(self, price):\n        self.price = price\n",
    "logger.info('price=%s status=%s', price, status)\n",
]
JS_TEMPLATES = [
    "const price = item.price;\n",
    "export function formatPrice(price_usd) {\n  return `$${price_usd.toFixed(2)}`;\n}\n",
    "// recompute price after discount\nconst finalPrice = price * (1 - discount);\n",
    "if (price_usd == null) { price_usd = estimatePrice(item); }\n",
    "console.log('price', price, 'discountedPrice', price * 0.9);\n",
]
MD_TEMPLATES = [
    "# Spider notes\n\nRetry policy: 3 attempts, backoff 2s.\n",
    "## Changelog\n\n- fixed pagination bug\n- added price normalization\n",
    "# Runbook\n\nCheck logs under logs/ for status=5xx spikes.\n",
]


def _write_lines(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def gen_filetree(rng: np.random.Generator) -> None:
    root = DATA_DIR / "filetree"

    n_days = scaled(3)
    lines_per_log = scaled(40)
    for day in range(1, n_days + 1):
        n_logs = scaled(4)
        for i in range(n_logs):
            lines = []
            for _ in range(lines_per_log):
                status = int(rng.choice(STATUS_POOL, p=STATUS_WEIGHTS))
                level = "ERROR" if status >= 500 else ("WARN" if status >= 400 else "INFO")
                price = round(float(rng.lognormal(3.2, 0.5)), 2)
                lines.append(
                    f"2026-07-{day:02d}T00:{i:02d}:{int(rng.integers(0, 60)):02d}Z "
                    f"{level} fetched url=https://example.test/p status={status} price={price}"
                )
            _write_lines(root / "logs" / f"day-{day:02d}" / f"spider-{i:02d}.log", lines)

    n_py = scaled(14)
    for i in range(n_py):
        template = PY_TEMPLATES[i % len(PY_TEMPLATES)]
        subdir = "core" if i % 2 == 0 else "utils"
        (root / "src" / subdir).mkdir(parents=True, exist_ok=True)
        (root / "src" / subdir / f"module_{i:03d}.py").write_text(template, encoding="utf-8")

    n_js = scaled(10)
    for i in range(n_js):
        template = JS_TEMPLATES[i % len(JS_TEMPLATES)]
        (root / "src" / "web").mkdir(parents=True, exist_ok=True)
        (root / "src" / "web" / f"widget_{i:03d}.js").write_text(template, encoding="utf-8")

    n_docs = scaled(8)
    for i in range(n_docs):
        template = MD_TEMPLATES[i % len(MD_TEMPLATES)]
        (root / "docs").mkdir(parents=True, exist_ok=True)
        (root / "docs" / f"note-{i:03d}.md").write_text(template, encoding="utf-8")

    n_config = scaled(6)
    config_subdirs = ["services", "env", "services/nested"]
    for i in range(n_config):
        subdir = config_subdirs[i % len(config_subdirs)]
        d = root / "config" / subdir
        d.mkdir(parents=True, exist_ok=True)
        payload = {"name": f"component-{i:03d}", "timeout_ms": int(rng.integers(100, 5000))}
        (d / f"component-{i:03d}.config.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")

    n_vendor_config = scaled(5)
    n_vendor_js = scaled(8)
    (root / "vendor" / "pkg").mkdir(parents=True, exist_ok=True)
    for i in range(n_vendor_config):
        payload = {"vendored": True, "id": i}
        (root / "vendor" / "pkg" / f"lib-{i:03d}.config.json").write_text(
            json.dumps(payload) + "\n", encoding="utf-8"
        )
    for i in range(n_vendor_js):
        (root / "vendor" / "pkg" / f"bundle-{i:03d}.js").write_text(
            "/* vendored, do not edit */\nmodule.exports = {};\n", encoding="utf-8"
        )


# --------------------------------------------------------------------------
# Task 03: warehouse CSV + partitioned Parquet
# --------------------------------------------------------------------------

def gen_warehouse(rng: np.random.Generator) -> None:
    out_dir = DATA_DIR / "warehouse"
    out_dir.mkdir(parents=True, exist_ok=True)

    n_products = scaled(120)
    product_ids = [f"WP{n:05d}" for n in range(1, n_products + 1)]
    categories = [CATEGORIES[i % len(CATEGORIES)] for i in range(n_products)]
    rng.shuffle(categories)  # deterministic given the seeded Generator
    regions = [REGIONS[int(rng.integers(0, len(REGIONS)))] for _ in range(n_products)]

    products_df = pd.DataFrame(
        {
            "product_id": product_ids,
            "category": categories,
            "region": regions,
            "listed_at": ["2026-01-15"] * n_products,
        }
    )
    products_df.to_csv(out_dir / "products.csv", index=False)

    n_obs_per_product = scaled(15)
    rows = []
    for pid, cat in zip(product_ids, categories):
        base_price = float(rng.lognormal(mean=3.5, sigma=0.5))
        price = base_price
        for k in range(n_obs_per_product):
            price = max(1.0, price + float(rng.normal(0, base_price * 0.04)))
            ts = f"2026-02-{(k % 27) + 1:02d}T{(k * 3) % 24:02d}:00:00"
            rows.append({"product_id": pid, "category": cat, "ts": ts, "price": round(price, 2)})

    obs_df = pd.DataFrame(rows)

    parquet_dir = out_dir / "parquet"
    if parquet_dir.exists():
        shutil.rmtree(parquet_dir)
    for cat in CATEGORIES:
        part = obs_df[obs_df["category"] == cat].drop(columns=["category"]).sort_values(
            ["product_id", "ts"]
        )
        if part.empty:
            continue
        cat_dir = parquet_dir / f"category={cat}"
        cat_dir.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(part, preserve_index=False)
        pq.write_table(table, cat_dir / "part-0.parquet")


# --------------------------------------------------------------------------
# Task 05: many small per-page input files for GNU parallel batch processing
# --------------------------------------------------------------------------

def gen_batch_inputs(rng: np.random.Generator) -> None:
    out_dir = DATA_DIR / "batch" / "inputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    n_files = scaled(30)
    for i in range(1, n_files + 1):
        source = SOURCES[int(rng.integers(0, len(SOURCES)))]
        n_listings = int(rng.integers(3, 9))
        listings = []
        for j in range(n_listings):
            category = CATEGORIES[int(rng.integers(0, len(CATEGORIES)))]
            price_cents = int(np.clip(rng.lognormal(mean=3.4, sigma=0.6) * 1000, 499, 49999))
            listings.append(
                {"listing_id": f"B{i:04d}-{j:02d}", "category": category, "price_cents": price_cents}
            )
        page = {"page_id": f"page-{i:04d}", "source_id": source["source_id"], "listings": listings}
        (out_dir / f"page-{i:04d}.json").write_text(json.dumps(page, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True)

    rng = np.random.default_rng(SEED)
    gen_catalog(rng)
    gen_filetree(rng)
    gen_warehouse(rng)
    gen_batch_inputs(rng)

    print(f"generated fixtures under {DATA_DIR} (SCALE={SCALE})")


if __name__ == "__main__":
    main()
