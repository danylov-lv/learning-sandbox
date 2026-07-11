"""Deterministic seeder for module 08's source Postgres (the CDC-captured
marketplace price DB) plus the deterministic change-workload builder later
tasks' validators reuse for reproducible insert/update/delete bursts.

Seeds shop.products and shop.offers directly in the SOURCE Postgres via
COPY -- this initial state is exactly what the Debezium snapshot phase
captures. Also writes data/ground-truth.json (committed), the answer key for
the snapshot-phase task. See .authoring/design.md for the full data contract.

Respects SCALE (default 1.0). Deterministic: a single seeded
np.random.default_rng(80808) stream. Draw order is fixed and documented in
design.md -- do not reorder without regenerating and updating every consumer.

Safe to rerun against a fresh or already-seeded stack: TRUNCATEs both tables
first, so this script is idempotent.

Usage:
    uv run python generate.py
    SCALE=0.1 uv run python generate.py
"""

import json
import math
import os
import sys
from pathlib import Path

import numpy as np

MODULE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import source_conninfo  # noqa: E402

SEED = 80808
DATA_DIR = MODULE_ROOT / "data"
GROUND_TRUTH_PATH = DATA_DIR / "ground-truth.json"

N_PRODUCTS_BASE = 5000
N_OFFERS_BASE = 20000
IN_STOCK_P = 0.85
BRAND_NULL_P = 0.15

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

NOUNS = {
    "electronics": ["Headphones", "Bluetooth Speaker", "Power Bank", "USB Hub", "Webcam", "Smartwatch"],
    "home-goods": ["Throw Pillow", "Wall Clock", "Area Rug", "Storage Bin", "Curtain Set", "Table Lamp"],
    "kitchen": ["Chef Knife", "Cutting Board", "Blender", "Coffee Grinder", "Mixing Bowl Set", "Non-Stick Pan"],
    "toys": ["Building Blocks", "Puzzle Set", "Remote Car", "Plush Toy", "Board Game", "Action Figure"],
    "sporting-goods": ["Yoga Mat", "Resistance Bands", "Water Bottle", "Running Shoes", "Dumbbell Set", "Bike Helmet"],
    "office-supplies": ["Notebook Pack", "Desk Organizer", "Stapler", "Sticky Notes", "Pen Set", "Whiteboard"],
    "beauty": ["Face Serum", "Lip Balm Set", "Hair Dryer", "Makeup Brush Set", "Body Lotion", "Nail Kit"],
    "apparel": ["Cotton T-Shirt", "Denim Jacket", "Wool Scarf", "Running Socks", "Baseball Cap", "Rain Jacket"],
}

ADJECTIVES = [
    "Premium", "Classic", "Pro", "Essential", "Deluxe",
    "Compact", "Ultra", "Everyday", "Signature", "Basic",
]

BRANDS = [
    "Nova", "Zenlite", "CraftWorks", "UrbanEdge", "Northlane",
    "Vitawell", "Pulsecore", "Ecomotion", "Brightline", "Solstice",
]

SELLERS = [
    "NovaMarket", "DealHive", "QuickCart Direct", "TrueValue Goods",
    "BrightBazaar", "PrimeSellers Co", "EverydayGoods", "SwiftTrade Outlet",
]

CURRENCIES = ["USD", "EUR", "GBP"]
CURRENCY_WEIGHTS = [0.60, 0.25, 0.15]

# Workload-burst prices are intentionally NOT category-aware (see
# build_workload docstring) -- a single generic price distribution.
WORKLOAD_PRICE_MEDIAN = 40.0
WORKLOAD_PRICE_SIGMA = 0.8


def category_weights():
    """Zipf popularity over categories: rank 0 (electronics) most popular."""
    ranks = np.arange(len(CATEGORIES))
    w = 1.0 / (ranks + 1) ** 1.1
    return w / w.sum()


def _product_universe(n_products, rng):
    """Draw order: category assignment, then popularity permutation. Shared
    by generate() so both product rows and offer->product weighting come
    from the same universe draw."""
    cat_w = category_weights()
    product_category_idx = rng.choice(len(CATEGORIES), size=n_products, p=cat_w)
    popularity_rank = rng.permutation(n_products) + 1
    pop_weight = 1.0 / popularity_rank ** 1.2
    pop_weight = pop_weight / pop_weight.sum()
    return product_category_idx, pop_weight


def generate():
    scale = float(os.environ.get("SCALE", "1.0"))
    rng = np.random.default_rng(SEED)
    n_products = max(1, int(round(N_PRODUCTS_BASE * scale)))
    n_offers = max(1, int(round(N_OFFERS_BASE * scale)))

    print(f"SCALE={scale} n_products={n_products} n_offers={n_offers}")

    # --- Universe ---
    product_category_idx, pop_weight = _product_universe(n_products, rng)

    # --- Products: brand assignment, then per-category title draws ---
    brand_is_null = rng.random(n_products) < BRAND_NULL_P
    brand_choice_idx = rng.integers(0, len(BRANDS), size=n_products)

    titles = [None] * n_products
    for ci, cat in enumerate(CATEGORIES):
        idx = np.where(product_category_idx == ci)[0]
        if idx.size == 0:
            continue
        nouns = NOUNS[cat]
        noun_choice = rng.integers(0, len(nouns), size=idx.size)
        adj_choice = rng.integers(0, len(ADJECTIVES), size=idx.size)
        for j, pi in enumerate(idx):
            titles[pi] = f"{ADJECTIVES[adj_choice[j]]} {nouns[noun_choice[j]]}"

    # --- Offers: product selection (Zipf via pop_weight), seller, currency,
    #     in_stock, then per-category lognormal prices ---
    product_ids = rng.choice(np.arange(1, n_products + 1), size=n_offers, p=pop_weight)
    cats_idx = product_category_idx[product_ids - 1]
    seller_idx = rng.integers(0, len(SELLERS), size=n_offers)
    currency_idx = rng.choice(len(CURRENCIES), size=n_offers, p=CURRENCY_WEIGHTS)
    in_stock = rng.random(n_offers) < IN_STOCK_P

    prices = np.zeros(n_offers)
    for ci, cat in enumerate(CATEGORIES):
        mask = cats_idx == ci
        cnt = int(mask.sum())
        if cnt:
            median, sigma = CATEGORY_PRICE_PROFILE[cat]
            prices[mask] = rng.lognormal(math.log(median), sigma, size=cnt)
    prices = np.round(prices, 2)

    # --- Load into source Postgres via COPY (idempotent: TRUNCATE first) ---
    import psycopg

    conn = psycopg.connect(source_conninfo())
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE shop.offers, shop.products RESTART IDENTITY CASCADE")

            with cur.copy("COPY shop.products (product_id, title, category, brand) FROM STDIN") as copy:
                for i in range(n_products):
                    brand = None if brand_is_null[i] else BRANDS[int(brand_choice_idx[i])]
                    copy.write_row((i + 1, titles[i], CATEGORIES[int(product_category_idx[i])], brand))

            with cur.copy(
                "COPY shop.offers (offer_id, product_id, seller, price, currency, in_stock) FROM STDIN"
            ) as copy:
                for i in range(n_offers):
                    copy.write_row((
                        i + 1,
                        int(product_ids[i]),
                        SELLERS[int(seller_idx[i])],
                        float(prices[i]),
                        CURRENCIES[int(currency_idx[i])],
                        bool(in_stock[i]),
                    ))
        conn.commit()
    finally:
        conn.close()

    # --- Ground truth (initial snapshot state -- the snapshot task's answer key) ---
    per_category_offer_counts = {
        cat: int((cats_idx == ci).sum()) for ci, cat in enumerate(CATEGORIES)
    }
    ground_truth = {
        "seed": SEED,
        "scale": scale,
        "n_products": n_products,
        "n_offers": n_offers,
        "constants": {
            "categories": CATEGORIES,
            "sellers": SELLERS,
            "currency_weights": dict(zip(CURRENCIES, CURRENCY_WEIGHTS)),
        },
        "row_counts": {"products": n_products, "offers": n_offers},
        "offers_price_sum": round(float(prices.sum()), 2),
        "distinct_products_with_offers": int(np.unique(product_ids).size),
        "per_category_offer_counts": per_category_offer_counts,
        "in_stock_count": int(in_stock.sum()),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_PATH.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    print(f"seeded shop.products ({n_products}) and shop.offers ({n_offers}) in source Postgres")
    print(f"ground truth written: {GROUND_TRUTH_PATH}")
    print(f"  offers_price_sum={ground_truth['offers_price_sum']} in_stock_count={ground_truth['in_stock_count']}")


def build_workload(seed, n_insert=0, n_update=0, n_delete=0,
                    n_products=N_PRODUCTS_BASE, n_offers=N_OFFERS_BASE):
    """Deterministic seeded change-workload builder, shared by later tasks'
    validators so a burst of inserts/updates/deletes against shop.offers is
    reproducible given (seed, n_insert, n_update, n_delete). Pure function --
    only BUILDS the op list, does not touch the database. Callers apply each
    op themselves (e.g. via psycopg) and observe the resulting Debezium
    change events.

    Returns a list of op dicts, updates first, then deletes, then inserts:
      {"op": "update", "table": "offers", "offer_id": int, "price": float, "in_stock": bool}
      {"op": "delete", "table": "offers", "offer_id": int}
      {"op": "insert", "table": "offers", "offer_id": int, "product_id": int,
       "seller": str, "price": float, "currency": str, "in_stock": bool}

    Assumes offer ids 1..n_offers and product ids 1..n_products already exist
    in the source (i.e. generate() has run at a SCALE producing at least that
    many rows -- the defaults match SCALE=1.0). Inserted offers get fresh ids
    starting at 1_000_000 + (seed % 100_000) * 100, so different seeds don't
    collide with each other or with seeded offer ids.

    Prices are drawn from a single generic lognormal distribution (median
    40, sigma 0.8), NOT the per-category profile generate() uses -- these are
    synthetic CDC-exercise bursts, not a second realistic corpus, so keeping
    the distribution category-agnostic keeps this function simple and fully
    self-contained (no dependency on the universe draw in generate()).
    """
    rng = np.random.default_rng(seed)
    ops = []

    n_update = max(0, min(n_update, n_offers))
    all_offer_ids = np.arange(1, n_offers + 1)
    update_ids = (
        rng.choice(all_offer_ids, size=n_update, replace=False)
        if n_update else np.array([], dtype=np.int64)
    )
    for oid in update_ids:
        price = round(float(rng.lognormal(math.log(WORKLOAD_PRICE_MEDIAN), WORKLOAD_PRICE_SIGMA)), 2)
        in_stock = bool(rng.random() < IN_STOCK_P)
        ops.append({"op": "update", "table": "offers", "offer_id": int(oid), "price": price, "in_stock": in_stock})

    remaining = np.setdiff1d(all_offer_ids, update_ids)
    n_delete = max(0, min(n_delete, remaining.size))
    delete_ids = (
        rng.choice(remaining, size=n_delete, replace=False)
        if n_delete else np.array([], dtype=np.int64)
    )
    for oid in delete_ids:
        ops.append({"op": "delete", "table": "offers", "offer_id": int(oid)})

    insert_base = 1_000_000 + (int(seed) % 100_000) * 100
    for i in range(n_insert):
        product_id = int(rng.integers(1, n_products + 1))
        seller = SELLERS[int(rng.integers(0, len(SELLERS)))]
        currency = CURRENCIES[int(rng.choice(len(CURRENCIES), p=CURRENCY_WEIGHTS))]
        price = round(float(rng.lognormal(math.log(WORKLOAD_PRICE_MEDIAN), WORKLOAD_PRICE_SIGMA)), 2)
        in_stock = bool(rng.random() < IN_STOCK_P)
        ops.append({
            "op": "insert", "table": "offers", "offer_id": insert_base + i,
            "product_id": product_id, "seller": seller, "price": price,
            "currency": currency, "in_stock": in_stock,
        })

    return ops


if __name__ == "__main__":
    sys.exit(generate())
