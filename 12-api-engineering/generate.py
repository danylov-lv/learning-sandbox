"""Deterministic generator for module 12 (API engineering).

Seeds Postgres DIRECTLY via COPY into schema `shop` -- the clean, properly-
indexed marketplace corpus the module's FastAPI tasks are built against (a
deliberately DIFFERENT stack from module 02's deliberately-wrecked schema;
see .authoring/design.md for the "own stack" decision and rationale). No
large files are written to disk; `data/` ends up holding ONLY the committed
`ground-truth.json` answer key.

Seed 121212 (`harness.common.SEED`, the single source of truth also used to
derive per-user password salts). Vectorized numpy throughout. Respects
`SCALE` (env, default 1.0):

    shop.sellers      2,000 * SCALE
    shop.categories   60 (fixed, independent of SCALE -- a small lookup tree)
    shop.products     200,000 * SCALE
    shop.users        20,000 * SCALE
    shop.orders       500,000 * SCALE
    shop.order_items  ~1,200,000 * SCALE (derived: ~2.4 items/order)

`GROUND_TRUTH_ONLY=1` recomputes/rewrites data/ground-truth.json from the
pure in-memory builders WITHOUT touching Postgres at all (mirrors module
09's affordance) -- also skips the (comparatively expensive) per-user
password hashing, since ground truth needs only row counts and money/qty
aggregates, never the hashes themselves.

Each `build_*` function is PURE (numpy + stdlib only, no file/DB I/O) and
independently seeded, so a validator can synthesize any one table's
in-memory corpus without replaying every other table's draws first. Exact
draw order per function is documented in .authoring/design.md -- reordering
any rng call invalidates the committed ground truth.

Usage:
    uv run python generate.py                       # SCALE=1.0
    SCALE=0.05 uv run python generate.py            # light local run
    GROUND_TRUTH_ONLY=1 uv run python generate.py   # rewrite answer key only, fast, no DB
"""

import json
import os
import sys
from datetime import date, datetime
from datetime import time as dtime
from datetime import timedelta, timezone
from pathlib import Path

import numpy as np

MODULE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    DATA_DIR,
    GROUND_TRUTH_PATH,
    SEED,
    pg_conn,
)

SEED_SELLERS = SEED + 1
SEED_PRODUCTS = SEED + 3
SEED_USERS = SEED + 4
SEED_ORDERS = SEED + 5
SEED_ORDER_ITEMS = SEED + 6

N_SELLERS_BASE = 2_000
N_PRODUCTS_BASE = 200_000
N_USERS_BASE = 20_000
N_ORDERS_BASE = 500_000

# ~18 months, ending at a fixed reference date (independent of wall-clock
# "today" so reruns on a different day stay byte-identical).
WINDOW_END = date(2026, 6, 30)
WINDOW_DAYS = 548
WINDOW_START = WINDOW_END - timedelta(days=WINDOW_DAYS - 1)

# Sellers/users get a longer look-back -- accounts predate the "recent"
# 18-month product/order window. No cross-table invariant is enforced
# (e.g. a product's created_at is not checked against its seller's
# created_at) -- see design.md's "known simplifications".
ACCOUNT_WINDOW_DAYS = 1095
ACCOUNT_WINDOW_START = WINDOW_END - timedelta(days=ACCOUNT_WINDOW_DAYS - 1)

FAMILIES = [
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

LEAF_NAMES = {
    "electronics": ["Headphones & Audio", "Smartphones", "Laptops & Computers",
                    "Cameras & Drones", "Wearables", "Smart Home", "Gaming Gear"],
    "home-goods": ["Lighting", "Rugs & Carpets", "Cushions & Throws",
                   "Curtains & Blinds", "Storage & Organization", "Wall Decor", "Furniture"],
    "kitchen": ["Cookware", "Knives & Cutlery", "Small Appliances",
                "Bakeware", "Kitchen Storage", "Tableware", "Coffee & Tea"],
    "toys": ["Building Sets", "Puzzles", "Action Figures",
             "Board Games", "Plush Toys", "Outdoor Toys", "Educational Toys"],
    "sporting-goods": ["Fitness Equipment", "Yoga & Wellness", "Cycling",
                        "Team Sports", "Camping & Hiking", "Footwear"],
    "office-supplies": ["Writing Instruments", "Paper Products", "Desk Organization",
                         "Filing & Storage", "Printers & Ink", "Office Furniture"],
    "beauty": ["Skincare", "Haircare", "Makeup", "Fragrances", "Bath & Body", "Tools & Accessories"],
    "apparel": ["T-Shirts & Tops", "Outerwear", "Denim", "Shoes", "Accessories", "Activewear"],
}

NOUNS = {
    "electronics": ["Headphones", "Bluetooth Speaker", "Power Bank", "Webcam", "Smartwatch", "Router"],
    "home-goods": ["Throw Pillow", "Wall Clock", "Area Rug", "Storage Bin", "Table Lamp", "Curtain Set"],
    "kitchen": ["Chef Knife", "Cutting Board", "Blender", "Coffee Grinder", "Mixing Bowl Set", "Non-Stick Pan"],
    "toys": ["Building Blocks", "Puzzle Set", "Remote Car", "Plush Toy", "Board Game", "Action Figure"],
    "sporting-goods": ["Yoga Mat", "Resistance Bands", "Water Bottle", "Running Shoes", "Dumbbell Set", "Bike Helmet"],
    "office-supplies": ["Notebook Pack", "Desk Organizer", "Stapler", "Sticky Notes", "Pen Set", "Whiteboard"],
    "beauty": ["Face Serum", "Lip Balm Set", "Hair Dryer", "Makeup Brush Set", "Body Lotion", "Nail Kit"],
    "apparel": ["Cotton T-Shirt", "Denim Jacket", "Wool Scarf", "Running Socks", "Baseball Cap", "Rain Jacket"],
}

ADJECTIVES = ["Premium", "Classic", "Pro", "Essential", "Deluxe",
              "Compact", "Ultra", "Everyday", "Signature", "Basic"]

BRANDS = ["Nova", "Zenlite", "CraftWorks", "UrbanEdge", "Northlane", "Vitawell",
          "Pulsecore", "Ecomotion", "Brightline", "Solstice", "Meridian", "Onyx",
          "Cobalt", "Aster", "Beacon", "Quill", "Terra", "Vivid", "Zephyr",
          "Halcyon", "Ridge", "Marlo", "Drift", "Cascade"]

ATTR_POOLS = {
    "color": ["black", "white", "red", "blue", "green", "silver", "gray", "gold"],
    "storage_gb": [64, 128, 256, 512, 1024],
    "warranty_months": [6, 12, 24, 36],
    "material": ["wood", "metal", "plastic", "glass", "cotton", "leather", "ceramic"],
    "dimensions_cm": ["20x20x10", "30x40x25", "15x15x15", "50x40x30", "10x10x5", "60x40x40"],
    "capacity_l": [0.5, 1.0, 1.5, 2.0, 3.0, 5.0],
    "age_range": ["0-3", "3-6", "6-9", "9-12", "12+"],
    "size": ["XS", "S", "M", "L", "XL"],
    "weight_kg": [0.2, 0.5, 1.0, 2.0, 5.0, 10.0],
    "pack_size": [1, 5, 10, 25, 50, 100],
    "volume_ml": [30, 50, 100, 200, 500],
    "scent": ["floral", "citrus", "woody", "fresh", "unscented"],
}

FAMILY_ATTR_FIELDS = {
    "electronics": ["color", "storage_gb", "warranty_months"],
    "home-goods": ["color", "material", "dimensions_cm"],
    "kitchen": ["material", "capacity_l", "color"],
    "toys": ["age_range", "material", "color"],
    "sporting-goods": ["color", "size", "weight_kg"],
    "office-supplies": ["color", "pack_size", "material"],
    "beauty": ["volume_ml", "scent", "color"],
    "apparel": ["color", "size", "material"],
}
SPEC_PRESENT_P = 0.75  # each family-specific attrs field present ~75% (absent ~25%)

SELLER_TIERS = ["bronze", "silver", "gold", "platinum"]
SELLER_TIER_WEIGHTS = [0.50, 0.30, 0.15, 0.05]

SELLER_WORD1 = ["Nova", "Bright", "Urban", "Prime", "Swift", "True", "Everyday", "North",
                "Vital", "Metro", "Silverline", "Golden", "Cedar", "Harbor", "Vertex",
                "Bluewave", "Solstice", "Crown", "Anchor", "Cobalt", "Amber", "Lumen",
                "Ridge", "Meridian"]
SELLER_WORD2 = ["Market", "Traders", "Goods", "Supply Co", "Outlet", "Emporium",
                "Bazaar", "Depot", "Collective", "Mercantile", "Exchange", "Warehouse"]

FIRST_NAMES = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
               "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph",
               "Jessica", "Thomas", "Sarah", "Charles", "Karen", "Daniel", "Nancy", "Matthew",
               "Lisa", "Anthony", "Betty", "Mark", "Margaret", "Donald", "Sandra", "Priya",
               "Wei", "Fatima", "Hiroshi", "Elena", "Carlos", "Amara", "Liam", "Noah", "Olivia"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
              "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
              "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
              "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
              "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores"]

COUNTRIES = ["United States", "Germany", "United Kingdom", "France", "Canada", "Spain",
             "Italy", "Netherlands", "Poland", "Sweden", "Brazil", "Mexico", "India",
             "Japan", "Australia"]

ORDER_STATUSES = ["completed", "shipped", "processing", "pending", "cancelled", "refunded"]
ORDER_STATUS_WEIGHTS = [0.50, 0.27, 0.08, 0.05, 0.06, 0.04]

ITEMS_PER_ORDER_CHOICES = np.array([1, 2, 3, 4, 5])
ITEMS_PER_ORDER_WEIGHTS = [0.30, 0.30, 0.20, 0.12, 0.08]  # expected ~2.38 items/order
QTY_CHOICES = np.array([1, 2, 3, 4, 5])
QTY_WEIGHTS = [0.55, 0.25, 0.12, 0.05, 0.03]


def _zipf_weights(k, s=1.1):
    ranks = np.arange(k)
    w = 1.0 / (ranks + 1) ** s
    return w / w.sum()


def category_weights():
    """Zipf popularity over the 52 leaf categories: rank 0 (the first leaf
    of the first family, in FAMILIES/LEAF_NAMES declaration order) is the
    most popular."""
    return _zipf_weights(52, 1.1)


def day_weights(n_days, start_weekday):
    """Cyclical/seasonal weighting over `n_days`: a weekly rhythm (weekends
    a little heavier), a gentle upward trend, and an annual sine-wave
    seasonality. Normalized to a probability vector."""
    days = np.arange(n_days)
    dow = (start_weekday + days) % 7
    weekly = np.where(dow >= 5, 1.15, 1.0)
    trend = 1.0 + 0.15 * (days / (n_days - 1))
    seasonal = 1.0 + 0.10 * np.sin(2 * np.pi * days / 365.0)
    w = weekly * trend * seasonal
    return w / w.sum()


def _window_ts(day, second):
    return datetime.combine(WINDOW_START, dtime.min, tzinfo=timezone.utc) + timedelta(days=int(day), seconds=int(second))


def _account_ts(day, second):
    return datetime.combine(ACCOUNT_WINDOW_START, dtime.min, tzinfo=timezone.utc) + timedelta(days=int(day), seconds=int(second))


_WINDOW_END_TS = datetime.combine(WINDOW_END, dtime(23, 59, 59), tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Pure builders -- numpy + stdlib only, no file/DB I/O. Each independently
# seeded so a validator can call any one of these without replaying the
# others' draws.
# --------------------------------------------------------------------------

def build_categories():
    """Pure, fully deterministic (NO rng): 8 family roots (depth 0) + 52
    leaves (depth 1) = 60 categories total, independent of SCALE (a fixed
    lookup/dimension table, like other modules' fixed category lists).
    ids are assigned 1..60 in a fixed order: roots first (FAMILIES order),
    then leaves grouped by family (FAMILIES order), each family's leaves in
    LEAF_NAMES[family] order. Returns a list of 60 dicts."""
    rows = []
    next_id = 1
    root_id_by_family = {}
    for family in FAMILIES:
        rows.append({
            "id": next_id, "parent_id": None,
            "name": family.replace("-", " ").title(),
            "family": family, "depth": 0,
        })
        root_id_by_family[family] = next_id
        next_id += 1
    for family in FAMILIES:
        for name in LEAF_NAMES[family]:
            rows.append({
                "id": next_id, "parent_id": root_id_by_family[family],
                "name": name, "family": family, "depth": 1,
            })
            next_id += 1
    return rows


def build_sellers(seed, n):
    """Pure: dict of arrays (id, name, tier, rating, created_at). Draw order
    SL1..SL6."""
    n = max(1, int(n))
    rng = np.random.default_rng(seed)

    w1_idx = rng.integers(0, len(SELLER_WORD1), size=n)                    # SL1
    w2_idx = rng.integers(0, len(SELLER_WORD2), size=n)                    # SL2
    tier_idx = rng.choice(len(SELLER_TIERS), size=n, p=SELLER_TIER_WEIGHTS)  # SL3
    rating = np.round(np.clip(rng.normal(4.2, 0.4, size=n), 1.0, 5.0), 2)  # SL4
    day = rng.integers(0, ACCOUNT_WINDOW_DAYS, size=n)                     # SL5
    second = rng.integers(0, 86400, size=n)                                # SL6

    ids = np.arange(1, n + 1)
    names = [f"{SELLER_WORD1[w1_idx[i]]} {SELLER_WORD2[w2_idx[i]]}" for i in range(n)]
    tiers = [SELLER_TIERS[int(t)] for t in tier_idx]
    created_at = [_account_ts(day[i], second[i]) for i in range(n)]

    return {"id": ids, "name": names, "tier": tiers, "rating": rating, "created_at": created_at}


def build_products(seed, n, n_sellers, leaf_ids):
    """Pure: dict of arrays/lists (id, seller_id, category_id, title, price,
    in_stock, attrs, created_at, updated_at). `leaf_ids` is the flat list of
    60-tree leaf category ids in build_categories()'s global order (used as
    the Zipf popularity ranking). Draw order P1..P13 (P13 runs inside a
    fixed-order per-family loop, see design.md)."""
    n = max(1, int(n))
    n_leaves = len(leaf_ids)
    rng = np.random.default_rng(seed)

    leaf_pos = rng.choice(n_leaves, size=n, p=category_weights())          # P1
    category_id = np.asarray(leaf_ids)[leaf_pos]
    leaf_counts = [len(LEAF_NAMES[f]) for f in FAMILIES]
    family_idx_of_leaf_pos = np.repeat(np.arange(len(FAMILIES)), leaf_counts)
    family_idx_of_row = family_idx_of_leaf_pos[leaf_pos]

    seller_pop_rank = rng.permutation(n_sellers) + 1                       # P2
    seller_pop_weight = 1.0 / seller_pop_rank ** 1.2
    seller_pop_weight = seller_pop_weight / seller_pop_weight.sum()
    seller_id = rng.choice(np.arange(1, n_sellers + 1), size=n, p=seller_pop_weight)  # P3

    medians = np.array([CATEGORY_PRICE_PROFILE[f][0] for f in FAMILIES])
    sigmas = np.array([CATEGORY_PRICE_PROFILE[f][1] for f in FAMILIES])
    z = rng.normal(size=n)                                                 # P4
    price = np.round(np.exp(np.log(medians[family_idx_of_row]) + sigmas[family_idx_of_row] * z), 2)
    np.clip(price, 0.5, None, out=price)

    in_stock = rng.random(n) < 0.88                                        # P5
    day_w = day_weights(WINDOW_DAYS, WINDOW_START.weekday())
    day = rng.choice(WINDOW_DAYS, size=n, p=day_w)                         # P6
    second = rng.integers(0, 86400, size=n)                                # P7
    update_delta_days = rng.integers(0, 91, size=n)                        # P8
    brand_idx = rng.integers(0, len(BRANDS), size=n)                       # P9
    adj_idx = rng.integers(0, len(ADJECTIVES), size=n)                     # P10
    spec_presence = rng.random((n, 3))                                     # P11
    spec_value = rng.random((n, 3))                                        # P12

    titles = [None] * n
    for fam_idx, family in enumerate(FAMILIES):                            # P13 (per family, fixed order)
        idx = np.where(family_idx_of_row == fam_idx)[0]
        if idx.size == 0:
            continue
        nouns = NOUNS[family]
        noun_choice = rng.integers(0, len(nouns), size=idx.size)
        for j, pi in enumerate(idx):
            titles[pi] = f"{ADJECTIVES[adj_idx[pi]]} {nouns[noun_choice[j]]}"

    created_at = [_window_ts(day[i], second[i]) for i in range(n)]
    updated_at = [min(created_at[i] + timedelta(days=int(update_delta_days[i])), _WINDOW_END_TS) for i in range(n)]

    attrs = []
    for i in range(n):
        family = FAMILIES[family_idx_of_row[i]]
        a = {"brand": BRANDS[brand_idx[i]]}
        for slot, field in enumerate(FAMILY_ATTR_FIELDS[family]):
            if spec_presence[i, slot] < SPEC_PRESENT_P:
                pool = ATTR_POOLS[field]
                vi = min(int(spec_value[i, slot] * len(pool)), len(pool) - 1)
                a[field] = pool[vi]
        attrs.append(a)

    return {
        "id": np.arange(1, n + 1), "seller_id": seller_id, "category_id": category_id,
        "title": titles, "price": price, "in_stock": in_stock, "attrs": attrs,
        "created_at": created_at, "updated_at": updated_at,
    }


def build_users(seed, n, compute_password_hash=True):
    """Pure: dict of arrays/lists (id, email, full_name, country,
    password_hash, created_at). Draw order U1..U5. Password hashing
    (parallelized scrypt over a thread pool -- see harness.common) is the
    only expensive part; skip it (compute_password_hash=False) for a fast
    ground-truth-only recompute, since ground truth never needs the hash
    itself."""
    n = max(1, int(n))
    rng = np.random.default_rng(seed)

    first_idx = rng.integers(0, len(FIRST_NAMES), size=n)   # U1
    last_idx = rng.integers(0, len(LAST_NAMES), size=n)     # U2
    country_idx = rng.integers(0, len(COUNTRIES), size=n)   # U3
    day = rng.integers(0, ACCOUNT_WINDOW_DAYS, size=n)      # U4
    second = rng.integers(0, 86400, size=n)                 # U5

    ids = np.arange(1, n + 1)
    full_names = [f"{FIRST_NAMES[first_idx[i]]} {LAST_NAMES[last_idx[i]]}" for i in range(n)]
    emails = [f"user{i}@kupitron-mail.example" for i in ids]
    countries = [COUNTRIES[int(c)] for c in country_idx]
    created_at = [_account_ts(day[i], second[i]) for i in range(n)]

    password_hash = _build_password_hashes(ids) if compute_password_hash else None

    return {
        "id": ids, "email": emails, "full_name": full_names, "country": countries,
        "password_hash": password_hash, "created_at": created_at,
    }


def _build_password_hashes(ids):
    """Threaded scrypt hashing (hashlib.scrypt releases the GIL, so threads
    give real speedup) -- see harness.common.build_user_password_hash for
    the per-user rule (build_password + deterministic salt)."""
    from concurrent.futures import ThreadPoolExecutor

    from harness.common import build_user_password_hash

    workers = min(32, (os.cpu_count() or 4) * 2)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(lambda uid: build_user_password_hash(int(uid)), ids))


def build_orders(seed, n, n_users):
    """Pure: dict of arrays (id, user_id, status, created_at). `total_amount`
    is NOT included here -- it is derived from build_order_items (an order's
    total is the sum of its line items, computed after order_items exist) and
    attached by the caller. Draw order O1..O4."""
    n = max(1, int(n))
    rng = np.random.default_rng(seed)

    user_id = rng.integers(1, n_users + 1, size=n)                          # O1
    status_idx = rng.choice(len(ORDER_STATUSES), size=n, p=ORDER_STATUS_WEIGHTS)  # O2
    day_w = day_weights(WINDOW_DAYS, WINDOW_START.weekday())
    day = rng.choice(WINDOW_DAYS, size=n, p=day_w)                          # O3
    second = rng.integers(0, 86400, size=n)                                 # O4

    ids = np.arange(1, n + 1)
    statuses = [ORDER_STATUSES[int(s)] for s in status_idx]
    created_at = [_window_ts(day[i], second[i]) for i in range(n)]

    return {"id": ids, "user_id": user_id, "status": statuses, "created_at": created_at}


def build_order_items(seed, order_ids, product_ids, product_prices):
    """Pure: (items_dict, order_total_array). `order_ids` MUST be the
    contiguous 1..n array build_orders() produces (order_total is indexed
    by order_id - 1). `product_ids`/`product_prices` are build_products()'s
    aligned id/price arrays. Draw order I1..I4:

      I1 items_per_order (1..5, skewed toward fewer items) per order
      I2 a Zipf popularity permutation over products (hot-seller demand)
      I3 product_pos per line item, drawn with that popularity weight
      I4 qty per line item (1..5, skewed toward 1)

    unit_price is looked up from product_prices at order-creation time (no
    independent price draw), so order_items and shop.products.price are
    always internally consistent -- orders_total_sum in ground truth is
    exactly sum(qty * unit_price) grouped by order, not a separate draw."""
    rng = np.random.default_rng(seed)
    n_orders = len(order_ids)

    items_per_order = rng.choice(ITEMS_PER_ORDER_CHOICES, size=n_orders, p=ITEMS_PER_ORDER_WEIGHTS)  # I1
    total_items = int(items_per_order.sum())
    order_id_col = np.repeat(order_ids, items_per_order)

    n_products = len(product_ids)
    pop_rank = rng.permutation(n_products) + 1                              # I2
    pop_weight = 1.0 / pop_rank ** 1.15
    pop_weight = pop_weight / pop_weight.sum()
    product_pos = rng.choice(n_products, size=total_items, p=pop_weight)    # I3
    product_id_col = np.asarray(product_ids)[product_pos]
    unit_price_col = np.round(np.asarray(product_prices)[product_pos], 2)

    qty_col = rng.choice(QTY_CHOICES, size=total_items, p=QTY_WEIGHTS)      # I4

    line_total = qty_col.astype(np.float64) * unit_price_col
    order_total = np.round(
        np.bincount(order_id_col - int(order_ids[0]), weights=line_total, minlength=n_orders), 2
    )

    items = {
        "id": np.arange(1, total_items + 1), "order_id": order_id_col,
        "product_id": product_id_col, "qty": qty_col, "unit_price": unit_price_col,
    }
    return items, order_total


# --------------------------------------------------------------------------
# Ground truth
# --------------------------------------------------------------------------

def _ground_truth(scale, categories, sellers, products, users, orders, order_items):
    price = products["price"]
    cat_id = products["category_id"]

    per_category_product_count = {
        str(c["id"]): int(np.count_nonzero(cat_id == c["id"])) for c in categories
    }

    # price desc, id asc tiebreak (np.lexsort's LAST key is primary)
    order = np.lexsort((products["id"], -price))
    top_idx = order[:20]
    top_products_by_price = [
        {"id": int(products["id"][i]), "price": float(price[i])} for i in top_idx
    ]

    return {
        "seed": SEED,
        "scale": scale,
        "row_counts": {
            "sellers": len(sellers["id"]), "categories": len(categories),
            "products": len(products["id"]), "users": len(users["id"]),
            "orders": len(orders["id"]), "order_items": len(order_items["id"]),
        },
        "products_price_sum": round(float(price.sum()), 2),
        "per_category_product_count": per_category_product_count,
        "orders_total_sum": round(float(orders["total_amount"].sum()), 2),
        "order_items_qty_sum": int(order_items["qty"].sum()),
        "products_id_checksum": int(products["id"].sum()),
        "top_products_by_price": top_products_by_price,
    }


# --------------------------------------------------------------------------
# Postgres load
# --------------------------------------------------------------------------

SCHEMA_SQL = """
DROP SCHEMA IF EXISTS shop CASCADE;
CREATE SCHEMA shop;

CREATE TABLE shop.sellers (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    tier        TEXT NOT NULL,
    rating      NUMERIC(3,2) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE shop.categories (
    id          INTEGER PRIMARY KEY,
    parent_id   INTEGER REFERENCES shop.categories (id),
    name        TEXT NOT NULL,
    family      TEXT NOT NULL,
    depth       SMALLINT NOT NULL
);
CREATE INDEX idx_categories_parent_id ON shop.categories (parent_id);

CREATE TABLE shop.products (
    id          BIGINT PRIMARY KEY,
    seller_id   INTEGER NOT NULL REFERENCES shop.sellers (id),
    category_id INTEGER NOT NULL REFERENCES shop.categories (id),
    title       TEXT NOT NULL,
    price       NUMERIC(12,2) NOT NULL,
    in_stock    BOOLEAN NOT NULL,
    attrs       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_products_seller_id ON shop.products (seller_id);
CREATE INDEX idx_products_category_id_id ON shop.products (category_id, id);
CREATE INDEX idx_products_created_at_id ON shop.products (created_at, id);
CREATE INDEX idx_products_attrs_gin ON shop.products USING GIN (attrs);

CREATE TABLE shop.users (
    id            INTEGER PRIMARY KEY,
    email         TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    country       TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX idx_users_email ON shop.users (email);

CREATE TABLE shop.orders (
    id           BIGINT PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES shop.users (id),
    status       TEXT NOT NULL,
    total_amount NUMERIC(12,2) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_orders_user_id_created_at ON shop.orders (user_id, created_at);

CREATE TABLE shop.order_items (
    id         BIGINT PRIMARY KEY,
    order_id   BIGINT NOT NULL REFERENCES shop.orders (id),
    product_id BIGINT NOT NULL REFERENCES shop.products (id),
    qty        SMALLINT NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL
);
CREATE INDEX idx_order_items_order_id ON shop.order_items (order_id);
"""


def _load_postgres(categories, sellers, products, users, orders, order_items):
    from psycopg.types.json import Jsonb

    conn = pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            conn.commit()

            with cur.copy("COPY shop.categories (id, parent_id, name, family, depth) FROM STDIN") as copy:
                for c in categories:
                    copy.write_row((c["id"], c["parent_id"], c["name"], c["family"], c["depth"]))
            conn.commit()

            with cur.copy("COPY shop.sellers (id, name, tier, rating, created_at) FROM STDIN") as copy:
                for i in range(len(sellers["id"])):
                    copy.write_row((
                        int(sellers["id"][i]), sellers["name"][i], sellers["tier"][i],
                        float(sellers["rating"][i]), sellers["created_at"][i],
                    ))
            conn.commit()

            with cur.copy(
                "COPY shop.products (id, seller_id, category_id, title, price, in_stock, attrs, "
                "created_at, updated_at) FROM STDIN"
            ) as copy:
                for i in range(len(products["id"])):
                    copy.write_row((
                        int(products["id"][i]), int(products["seller_id"][i]), int(products["category_id"][i]),
                        products["title"][i], float(products["price"][i]), bool(products["in_stock"][i]),
                        Jsonb(products["attrs"][i]), products["created_at"][i], products["updated_at"][i],
                    ))
            conn.commit()

            with cur.copy(
                "COPY shop.users (id, email, full_name, country, password_hash, created_at) FROM STDIN"
            ) as copy:
                for i in range(len(users["id"])):
                    copy.write_row((
                        int(users["id"][i]), users["email"][i], users["full_name"][i], users["country"][i],
                        users["password_hash"][i], users["created_at"][i],
                    ))
            conn.commit()

            with cur.copy("COPY shop.orders (id, user_id, status, total_amount, created_at) FROM STDIN") as copy:
                for i in range(len(orders["id"])):
                    copy.write_row((
                        int(orders["id"][i]), int(orders["user_id"][i]), orders["status"][i],
                        float(orders["total_amount"][i]), orders["created_at"][i],
                    ))
            conn.commit()

            with cur.copy(
                "COPY shop.order_items (id, order_id, product_id, qty, unit_price) FROM STDIN"
            ) as copy:
                for i in range(len(order_items["id"])):
                    copy.write_row((
                        int(order_items["id"][i]), int(order_items["order_id"][i]),
                        int(order_items["product_id"][i]), int(order_items["qty"][i]),
                        float(order_items["unit_price"][i]),
                    ))
            conn.commit()
    finally:
        conn.close()


def generate():
    scale = float(os.environ.get("SCALE", "1.0"))
    ground_truth_only = os.environ.get("GROUND_TRUTH_ONLY", "") not in ("", "0", "false")

    n_sellers = max(1, int(round(N_SELLERS_BASE * scale)))
    n_products = max(1, int(round(N_PRODUCTS_BASE * scale)))
    n_users = max(1, int(round(N_USERS_BASE * scale)))
    n_orders = max(1, int(round(N_ORDERS_BASE * scale)))

    print(f"SCALE={scale} GROUND_TRUTH_ONLY={ground_truth_only} "
          f"n_sellers={n_sellers} n_products={n_products} n_users={n_users} n_orders={n_orders}")

    categories = build_categories()
    leaf_ids = [c["id"] for c in categories if c["depth"] == 1]

    sellers = build_sellers(SEED_SELLERS, n_sellers)
    products = build_products(SEED_PRODUCTS, n_products, n_sellers, leaf_ids)
    users = build_users(SEED_USERS, n_users, compute_password_hash=not ground_truth_only)
    orders = build_orders(SEED_ORDERS, n_orders, n_users)
    order_items, order_total = build_order_items(
        SEED_ORDER_ITEMS, orders["id"], products["id"], products["price"]
    )
    orders["total_amount"] = order_total

    print(f"built arrays: sellers={len(sellers['id'])} categories={len(categories)} "
          f"products={len(products['id'])} users={len(users['id'])} orders={len(orders['id'])} "
          f"order_items={len(order_items['id'])}")

    gt = _ground_truth(scale, categories, sellers, products, users, orders, order_items)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_PATH.write_text(json.dumps(gt, indent=2), encoding="utf-8")
    print(f"ground truth written: {GROUND_TRUTH_PATH}")
    print(f"  row_counts={gt['row_counts']}")
    print(f"  products_price_sum={gt['products_price_sum']} orders_total_sum={gt['orders_total_sum']} "
          f"order_items_qty_sum={gt['order_items_qty_sum']} products_id_checksum={gt['products_id_checksum']}")

    if ground_truth_only:
        print("GROUND_TRUTH_ONLY: skipped Postgres load (and password hashing)")
        return

    print("loading Postgres schema `shop` ...")
    _load_postgres(categories, sellers, products, users, orders, order_items)
    print("done.")


if __name__ == "__main__":
    sys.exit(generate())
