"""Deterministic generator for module 14 (stats and ML foundations).

Builds ONE shared dataset used by all 13 tasks: a realistic "scraped
product-price" corpus with planted data-quality defects (bad price parses,
un-normalized currency), a genuine log-normal outlier tail, and a
Simpson's-paradox-flavored confound between discount_pct and units_sold
(see CATEGORY_BASE_DISCOUNT / CATEGORY_BASE_UNITS / WITHIN_CATEGORY_EFFECT
below, and .authoring/design.md for the full writeup).

  * data/observations.parquet — GITIGNORED. One row per scrape observation.
    Written via pyarrow. See harness/common.py OBSERVATIONS_PATH.
  * data/ground-truth.json    — COMMITTED. Answer key computed by
    aggregating the built DataFrame (never hand-computed / hardcoded):
    counts, defect breakdown, valid-price stats, outlier count, data_sha.

`build_observations(seed, n) -> (df, labels)` is PURE (numpy + pandas only,
no file I/O) so a validator can reconstruct the dataset and its hidden
labels (defect kind, non-USD flag, genuine-outlier flag, the confound's
category-level reference tables) in-memory without reading a hidden file —
mirrors module 10/11's pure-builder pattern.

Deterministic: fixed seed 141414, fixed draw order G1..G12 (see
.authoring/design.md — do not reorder without regenerating and updating
every consumer). Respects `SCALE` (env, default 1.0):
`n_obs = round(60000 * SCALE)`, `n_products = round(n_obs / 7.5)`.

Usage:
    uv run python generate.py                # SCALE=1.0 (60000 observations)
    SCALE=0.05 uv run python generate.py      # fast smoke run
    GROUND_TRUTH_ONLY=1 uv run python generate.py  # rewrite ground-truth.json only, skip parquet
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MODULE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import DATA_DIR, GROUND_TRUTH_PATH, OBSERVATIONS_PATH  # noqa: E402

SEED = 141414
N_OBS_BASE = 60000
PRODUCTS_PER_OBS_RATIO = 7.5

CATEGORIES = [
    "electronics", "home-goods", "kitchen", "toys", "sporting-goods", "apparel", "books", "garden",
]

# (median, sigma) for a log-normal price draw per category.
CATEGORY_PRICE_PROFILE = {
    "electronics": (150.0, 0.90),
    "home-goods": (45.0, 0.65),
    "kitchen": (34.0, 0.55),
    "toys": (22.0, 0.50),
    "sporting-goods": (58.0, 0.70),
    "apparel": (28.0, 0.50),
    "books": (14.0, 0.35),
    "garden": (38.0, 0.60),
}

# Title vocabulary: 4 brand tokens + 6 noun tokens per category, so
# rng.integers(0, 4/6, size=n) can index uniformly across categories.
CATEGORY_TOKENS = {
    "electronics": {
        "brands": ["Voltix", "Nexara", "Photron", "Quantek"],
        "nouns": ["headphones", "monitor", "router", "speaker", "tablet", "charger"],
    },
    "home-goods": {
        "brands": ["Hearthly", "Domora", "Linenfolk", "Cozyma"],
        "nouns": ["lamp", "rug", "curtain", "pillow", "organizer", "candle"],
    },
    "kitchen": {
        "brands": ["Cookaro", "Panvista", "Brewline", "Choppex"],
        "nouns": ["blender", "skillet", "kettle", "cutting-board", "mixer", "thermos"],
    },
    "toys": {
        "brands": ["Funkerie", "Playbrick", "Wondera", "Tumblex"],
        "nouns": ["building-set", "plush-bear", "puzzle", "action-figure", "toy-car", "drone-toy"],
    },
    "sporting-goods": {
        "brands": ["Trailforge", "Pacefit", "Ironclad", "Summitgear"],
        "nouns": ["yoga-mat", "dumbbell-set", "running-shoes", "bike-helmet", "tent", "water-bottle"],
    },
    "apparel": {
        "brands": ["Threadloom", "Urbanwear", "Cottona", "Fibrance"],
        "nouns": ["hoodie", "t-shirt", "jeans", "jacket", "socks", "scarf"],
    },
    "books": {
        "brands": ["Pageforge", "Inkwell", "Storybound", "Chapterhouse"],
        "nouns": ["novel", "cookbook", "field-guide", "biography", "atlas", "journal"],
    },
    "garden": {
        "brands": ["Greenhold", "Bloomcraft", "Soilwise", "Rootline"],
        "nouns": ["planter", "hose", "pruning-shears", "trellis", "fertilizer", "wheelbarrow"],
    },
}

ADJECTIVES = [
    "Compact", "Premium", "Deluxe", "Classic", "Pro", "Eco", "Portable", "Heavy-Duty", "Slim", "Rustic",
]

# Shared across all categories (a "generic brand" pool, e.g. a marketplace's
# own house brand) — diluting brand as a perfect category signal so a
# title-only classifier has real work to do instead of memorizing brand.
GENERIC_BRANDS = ["Zenmark", "Corebase", "Vantay", "Northlane"]
GENERIC_BRAND_FRAC = 0.30

CROSS_NOUN_NOISE_FRAC = 0.25  # fraction of titles that borrow a noun from a different category

CURRENCIES_NON_USD = ["EUR", "GBP"]
NON_USD_FRAC = 0.02

SOURCE_SITES = ["alpha-shop", "beta-mart", "gamma-store"]
SOURCE_SITE_WEIGHTS = [0.5, 0.3, 0.2]

SCRAPE_WINDOW_DAYS = 90
SCRAPE_WINDOW_END = pd.Timestamp("2026-01-01")  # fixed, not "today" — keeps generation reproducible

DEFECT_FRAC = 0.045  # total fraction of rows with a planted price defect
DEFECT_KINDS = ["negative", "zero", "missing_decimal", "nan"]

OUTLIER_PCTILE = 99.5  # per-category percentile of the CLEAN draw defining "genuine outlier"

# Simpson's-paradox confound: discount_pct and units_sold are both driven by
# category (cheap/impulse categories discount more AND sell more), so the
# POOLED correlation is strongly positive. The WITHIN-category effect of
# discount_pct on units_sold is deliberately weak (see WITHIN_CATEGORY_EFFECT)
# — task 09 recomputes pooled vs. per-category slopes against these tables.
CATEGORY_BASE_DISCOUNT = {
    "electronics": 0.08,
    "home-goods": 0.15,
    "kitchen": 0.18,
    "toys": 0.30,
    "sporting-goods": 0.10,
    "apparel": 0.35,
    "books": 0.25,
    "garden": 0.20,
}
CATEGORY_BASE_UNITS = {
    "electronics": 15.0,
    "home-goods": 25.0,
    "kitchen": 30.0,
    "toys": 60.0,
    "sporting-goods": 20.0,
    "apparel": 55.0,
    "books": 45.0,
    "garden": 28.0,
}
DISCOUNT_NOISE_SIGMA = 0.05
WITHIN_CATEGORY_EFFECT = 0.10  # weak true effect of within-category discount deviation on units lambda


def _zipf_weights(k, s=1.1):
    ranks = np.arange(k)
    w = 1.0 / (ranks + 1) ** s
    return w / w.sum()


def category_weights():
    return _zipf_weights(len(CATEGORIES), 1.1)


# Flatter than category popularity (1.1) on purpose: at s=1.1 over an 8000-
# product pool, ~60000 draws would only ever touch ~5400 distinct products
# (heavy Zipf tail starves most of the pool). s=0.4 keeps "popular products
# get scraped more" while still touching close to the full ~8000-product pool.
PRODUCT_POPULARITY_S = 0.4


def build_observations(seed, n):
    """Pure builder: (DataFrame, labels). Numpy-vectorized numeric draws, no
    Python row loops for prices/timestamps/etc. — title string assembly uses
    a vectorized index draw plus a single list-comprehension format pass
    (unavoidable for per-row string formatting in pure Python/numpy).

    Draw order (fixed, do not reorder — see .authoring/design.md):
      G1  product category assignment (Zipf over CATEGORIES, per product)
      G2  product popularity weights (Zipf over product_id rank; no rng draw)
      G3  observation -> product assignment (Zipf-weighted choice)
      G4  clean price (log-normal per category)
      G5  title tokens (brand/adj/noun/model + cross-category noise)
      G6  currency (non-USD subset)
      G7  scraped_at (weekly + daily cyclicality)
      G8  in_stock
      G9  seller_rating
      G10 source_site
      G11 discount_pct + units_sold (confounded by category)
      G12 price defect selection + application
    """
    n = max(1, int(n))
    n_products = max(1, round(n / PRODUCTS_PER_OBS_RATIO))
    n_cat = len(CATEGORIES)
    rng = np.random.default_rng(seed)

    # G1
    product_category_idx = rng.choice(n_cat, size=n_products, p=category_weights())

    # G2 (deterministic weights, no rng draw)
    product_weights = _zipf_weights(n_products, PRODUCT_POPULARITY_S)

    # G3
    obs_product_idx = rng.choice(n_products, size=n, p=product_weights)
    category_idx = product_category_idx[obs_product_idx]
    category_arr = np.array(CATEGORIES)[category_idx]

    # G4
    medians = np.array([CATEGORY_PRICE_PROFILE[c][0] for c in CATEGORIES])
    sigmas = np.array([CATEGORY_PRICE_PROFILE[c][1] for c in CATEGORIES])
    z = rng.normal(size=n)
    clean_price = np.round(np.exp(np.log(medians[category_idx]) + sigmas[category_idx] * z), 2)
    np.clip(clean_price, 0.5, None, out=clean_price)

    # G5 — title tokens
    brand_idx = rng.integers(0, 4, size=n)
    adj_idx = rng.integers(0, len(ADJECTIVES), size=n)
    noun_idx = rng.integers(0, 6, size=n)
    model_num = rng.integers(100, 999, size=n)
    model_letter_idx = rng.integers(0, 26, size=n)
    cross_noise_roll = rng.random(size=n) < CROSS_NOUN_NOISE_FRAC
    cross_cat_offset = rng.integers(1, n_cat, size=n)  # 1..n_cat-1, guarantees a different category
    cross_cat_idx = (category_idx + cross_cat_offset) % n_cat
    generic_brand_roll = rng.random(size=n) < GENERIC_BRAND_FRAC

    brands_by_cat = [CATEGORY_TOKENS[c]["brands"] for c in CATEGORIES]
    nouns_by_cat = [CATEGORY_TOKENS[c]["nouns"] for c in CATEGORIES]

    titles = []
    for i in range(n):
        cat_i = category_idx[i]
        brand = GENERIC_BRANDS[brand_idx[i]] if generic_brand_roll[i] else brands_by_cat[cat_i][brand_idx[i]]
        adj = ADJECTIVES[adj_idx[i]]
        noun_cat_i = cross_cat_idx[i] if cross_noise_roll[i] else cat_i
        noun = nouns_by_cat[noun_cat_i][noun_idx[i]]
        model = f"{chr(65 + model_letter_idx[i])}{model_num[i]}"
        titles.append(f"{brand} {adj} {noun} {model}")

    # G6 — currency
    non_usd_roll = rng.random(size=n) < NON_USD_FRAC
    non_usd_code_idx = rng.integers(0, len(CURRENCIES_NON_USD), size=n)
    currency = np.where(
        non_usd_roll,
        np.array(CURRENCIES_NON_USD)[non_usd_code_idx],
        "USD",
    )

    # G7 — scraped_at: weekday-biased day pick + a daytime-clustered hour
    day_of_week = np.arange(SCRAPE_WINDOW_DAYS) % 7
    day_weight = np.where(day_of_week < 5, 1.3, 0.7)
    day_weight = day_weight / day_weight.sum()
    day_offset = rng.choice(SCRAPE_WINDOW_DAYS, size=n, p=day_weight)
    hour_frac = np.clip(rng.normal(13.0, 4.0, size=n), 0.0, 23.99)
    start = SCRAPE_WINDOW_END - pd.Timedelta(days=SCRAPE_WINDOW_DAYS)
    scraped_at = (
        start
        + pd.to_timedelta(day_offset, unit="D")
        + pd.to_timedelta(np.round(hour_frac * 3600).astype(int), unit="s")
    )

    # G8
    in_stock = rng.random(size=n) < 0.85

    # G9
    seller_rating = np.round(np.clip(rng.normal(4.2, 0.5, size=n), 1.0, 5.0), 1)

    # G10
    site_idx = rng.choice(len(SOURCE_SITES), size=n, p=SOURCE_SITE_WEIGHTS)
    source_site = np.array(SOURCE_SITES)[site_idx]

    # G11 — discount_pct / units_sold confound
    base_discount_arr = np.array([CATEGORY_BASE_DISCOUNT[c] for c in CATEGORIES])[category_idx]
    base_units_arr = np.array([CATEGORY_BASE_UNITS[c] for c in CATEGORIES])[category_idx]
    discount_noise = rng.normal(0.0, DISCOUNT_NOISE_SIGMA, size=n)
    discount_pct = np.round(np.clip(base_discount_arr + discount_noise, 0.0, 0.6), 3)
    lambda_units = np.maximum(
        base_units_arr * (1.0 + WITHIN_CATEGORY_EFFECT * (discount_pct - base_discount_arr)), 0.5
    )
    units_sold = rng.poisson(lambda_units)

    # G12 — plant price defects on a fixed subset
    total_defect_n = round(DEFECT_FRAC * n)
    defect_idx = rng.choice(n, size=total_defect_n, replace=False)
    chunks = np.array_split(defect_idx, len(DEFECT_KINDS))
    kind_idx = dict(zip(DEFECT_KINDS, chunks))

    price = clean_price.copy()
    defect_mask = np.zeros(n, dtype=bool)
    defect_kind = np.full(n, "", dtype=object)

    price[kind_idx["negative"]] = -price[kind_idx["negative"]]
    price[kind_idx["zero"]] = 0.0
    price[kind_idx["missing_decimal"]] = np.round(price[kind_idx["missing_decimal"]] * 100, 2)
    price[kind_idx["nan"]] = np.nan
    for kind, idx in kind_idx.items():
        defect_mask[idx] = True
        defect_kind[idx] = kind

    # genuine outliers: per-category p99.5 of the CLEAN draw, among rows that
    # end up valid (no defect, USD currency)
    non_usd_mask = non_usd_roll
    valid_mask = (~defect_mask) & (~non_usd_mask)
    genuine_outlier_mask = np.zeros(n, dtype=bool)
    for ci, c in enumerate(CATEGORIES):
        cat_rows = category_idx == ci
        if not cat_rows.any():
            continue
        threshold = np.percentile(clean_price[cat_rows], OUTLIER_PCTILE)
        genuine_outlier_mask |= cat_rows & valid_mask & (clean_price > threshold)

    obs_id = np.arange(1, n + 1)
    product_id = obs_product_idx + 1

    df = pd.DataFrame({
        "obs_id": obs_id,
        "product_id": product_id,
        "category": category_arr,
        "title": titles,
        "price": price,
        "currency": currency,
        "scraped_at": scraped_at,
        "in_stock": in_stock,
        "seller_rating": seller_rating,
        "source_site": source_site,
        "discount_pct": discount_pct,
        "units_sold": units_sold,
    })

    labels = {
        "clean_price": clean_price,
        "defect_mask": defect_mask,
        "defect_kind": defect_kind,
        "non_usd_mask": non_usd_mask,
        "genuine_outlier_mask": genuine_outlier_mask,
        "valid_mask": valid_mask,
        "product_category": np.array(CATEGORIES)[product_category_idx],  # index by product_id - 1
        "category_price_profile": CATEGORY_PRICE_PROFILE,
        "confound": {
            "category_base_discount": CATEGORY_BASE_DISCOUNT,
            "category_base_units": CATEGORY_BASE_UNITS,
            "discount_noise_sigma": DISCOUNT_NOISE_SIGMA,
            "within_category_effect": WITHIN_CATEGORY_EFFECT,
        },
    }
    return df, labels


def _data_sha(df):
    csv_bytes = df.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(csv_bytes).hexdigest()


def _ground_truth(df, labels, seed, scale):
    valid_mask = labels["valid_mask"]
    valid_price = df["price"].to_numpy()[valid_mask]

    per_category_count = df["category"].value_counts().reindex(CATEGORIES, fill_value=0).to_dict()
    per_category_count_valid = (
        df.loc[valid_mask, "category"].value_counts().reindex(CATEGORIES, fill_value=0).to_dict()
    )

    defect_kind = labels["defect_kind"]
    kind_counts = {k: int((defect_kind == k).sum()) for k in DEFECT_KINDS}

    return {
        "seed": seed,
        "scale": scale,
        "n_obs": len(df),
        "n_products": int(df["product_id"].nunique()),
        "categories": CATEGORIES,
        "per_category_count": {k: int(v) for k, v in per_category_count.items()},
        "per_category_count_valid": {k: int(v) for k, v in per_category_count_valid.items()},
        "n_parsing_errors": int(labels["defect_mask"].sum()),
        "parsing_error_kind_counts": kind_counts,
        "n_non_usd": int(labels["non_usd_mask"].sum()),
        "n_nan_price": kind_counts["nan"],
        "valid_price_sum": round(float(np.sum(valid_price)), 2),
        "valid_price_mean": round(float(np.mean(valid_price)), 2),
        "valid_price_median": round(float(np.median(valid_price)), 2),
        "valid_price_p99": round(float(np.percentile(valid_price, 99)), 2),
        "n_genuine_outliers": int(labels["genuine_outlier_mask"].sum()),
        "data_sha": _data_sha(df),
    }


def generate():
    scale = float(os.environ.get("SCALE", "1.0"))
    ground_truth_only = os.environ.get("GROUND_TRUTH_ONLY", "") not in ("", "0", "false")
    n_obs = max(1, round(N_OBS_BASE * scale))

    print(f"SCALE={scale} GROUND_TRUTH_ONLY={ground_truth_only} n_obs={n_obs}")

    df, labels = build_observations(SEED, n_obs)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not ground_truth_only:
        df.to_parquet(OBSERVATIONS_PATH, engine="pyarrow", index=False)
        print(f"wrote {OBSERVATIONS_PATH.name} ({len(df)} rows)")
    else:
        print("GROUND_TRUTH_ONLY: skipped parquet write")

    gt = _ground_truth(df, labels, SEED, scale)
    GROUND_TRUTH_PATH.write_text(json.dumps(gt, indent=2), encoding="utf-8")
    print(f"ground truth written: {GROUND_TRUTH_PATH}")
    print(f"  n_obs={gt['n_obs']} n_products={gt['n_products']}")
    print(f"  per_category_count={gt['per_category_count']}")
    print(f"  n_parsing_errors={gt['n_parsing_errors']} kinds={gt['parsing_error_kind_counts']}")
    print(f"  n_non_usd={gt['n_non_usd']} n_genuine_outliers={gt['n_genuine_outliers']}")
    print(f"  valid_price_mean={gt['valid_price_mean']} valid_price_median={gt['valid_price_median']} valid_price_p99={gt['valid_price_p99']}")
    print(f"  data_sha={gt['data_sha']}")


if __name__ == "__main__":
    sys.exit(generate())
