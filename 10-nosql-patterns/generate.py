"""Deterministic generator for module 10 (NoSQL patterns: Redis + MongoDB +
Postgres JSONB).

Builds two corpora over a scraping domain and writes them as NDJSON (one JSON
object per line), both GITIGNORED:

  * data/products.json  — SEMI-STRUCTURED scraped product documents whose
    `specs` keys depend on category and are randomly absent, an embedded
    `seller` sub-document, and a multikey `tags` array. Feeds the document
    modeling / Mongo-vs-JSONB tasks (05, 06).
  * data/events.json    — a stream of scrape hits (one observation per line),
    each scraping a REAL catalog product, with a KNOWN ~30% duplicate-url rate
    and Zipf-skewed domains. Feeds the dedup / streams / rate-limiter tasks
    (01-04) and the capstone (08).

Also writes data/ground-truth.json (COMMITTED), the answer key every validator
grades against — computed purely from the numpy/python arrays, independent of
any database. No database is touched here: each task loads Redis / Mongo /
Postgres itself, differently, so loading is a task concern, not a generator
one.

Deterministic: fixed seeds (products 10101, events 10102) and a fixed draw
order (documented in .authoring/design.md — do not reorder without
regenerating and updating every consumer). Respects `SCALE` (env, default
1.0): `n_events = round(25000 * SCALE)`, `n_products = round(20000 * SCALE)`.
Both are small on purpose — Mongo / JSONB / Redis do not need millions of rows.

`build_products(seed, n)` and `build_events(seed, n, products)` are PURE
(numpy/python only, no DB, no file I/O) and return lists of dicts, so
validators can import them for deterministic in-memory workloads; events are
coupled to the catalog, so `build_events` takes the product list.

Usage:
    uv run python generate.py                # SCALE=1.0 (20k products, 25k events)
    SCALE=0.1 uv run python generate.py      # light run
"""

import json
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np

MODULE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    DATA_DIR,
    EVENTS_PATH,
    GROUND_TRUTH_PATH,
    PRODUCTS_PATH,
)

SEED_PRODUCTS = 10101
SEED_EVENTS = 10102

N_PRODUCTS_BASE = 20_000
N_EVENTS_BASE = 25_000       # keeps unique urls (<= n_products) at ~70% for a ~30% dup rate

N_SELLERS = 200
DUP_UNIQUE_FRACTION = 0.70   # ~70% of events scrape a not-yet-seen product => ~30% duplicates
IN_STOCK_P = 0.85
SPEC_PRESENT_P = 0.80        # each category spec key present ~80% (absent ~20%)
EVENT_PRICE_SIGMA = 0.08     # per-scrape log jitter around the product's catalog price

WINDOW_END = date(2025, 6, 30)
WINDOW_DAYS = 90
WINDOW_START = WINDOW_END - timedelta(days=WINDOW_DAYS - 1)

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

CATEGORY_NOUNS = {
    "electronics": ["Headphones", "Charger", "Speaker", "Monitor", "Webcam"],
    "home-goods": ["Lamp", "Rug", "Cushion", "Curtain", "Vase"],
    "kitchen": ["Pot", "Knife", "Blender", "Kettle", "Pan"],
    "toys": ["Blocks", "Puzzle", "Figure", "Board Game", "Plush"],
    "sporting-goods": ["Dumbbell", "Yoga Mat", "Bottle", "Racket", "Gloves"],
    "office-supplies": ["Notebook", "Pen Set", "Stapler", "Folder", "Marker"],
    "beauty": ["Serum", "Lotion", "Lipstick", "Perfume", "Cream"],
    "apparel": ["T-Shirt", "Hoodie", "Jacket", "Socks", "Cap"],
}

DOMAINS = [
    "shopmart.example", "megadeals.example", "buyhub.example",
    "pricepeek.example", "bargainbay.example",
]

BRANDS = [
    "Acme", "Nimbus", "Vertex", "Orbit", "Pioneer", "Cascade", "Summit",
    "Lumen", "Harbor", "Meridian", "Onyx", "Cobalt", "Aster", "Beacon",
    "Fable", "Quill", "Terra", "Vivid", "Zephyr", "Halcyon", "Ridge",
    "Marlo", "Nova", "Drift",
]

TAGS = ["sale", "new", "bestseller", "clearance", "eco", "imported"]
N_TAGS = len(TAGS)

SPEC_POOLS = {
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

CATEGORY_SPECS = {
    "electronics": ["color", "storage_gb", "warranty_months"],
    "home-goods": ["color", "material", "dimensions_cm"],
    "kitchen": ["material", "capacity_l", "color"],
    "toys": ["age_range", "material", "color"],
    "sporting-goods": ["color", "size", "weight_kg"],
    "office-supplies": ["color", "pack_size", "material"],
    "beauty": ["volume_ml", "scent", "color"],
    "apparel": ["color", "size", "material"],
}

CURRENCIES = ["USD", "EUR", "GBP"]
CURRENCY_WEIGHTS = [0.60, 0.25, 0.15]


def _zipf_weights(k, s=1.1):
    ranks = np.arange(k)
    w = 1.0 / (ranks + 1) ** s
    return w / w.sum()


def category_weights():
    return _zipf_weights(len(CATEGORIES), 1.1)


def domain_weights():
    return _zipf_weights(len(DOMAINS), 1.1)


def brand_weights():
    return _zipf_weights(len(BRANDS), 1.05)


def _seller_names(seed):
    """Deterministic pool of seller display names. Faker only for text; it
    feeds no ground-truth key, so its exact strings are cosmetic."""
    from faker import Faker

    fake = Faker()
    Faker.seed(seed)
    return [fake.company() for _ in range(N_SELLERS)]


def _iso(day, second):
    return (datetime.combine(WINDOW_START, time.min)
            + timedelta(days=int(day), seconds=int(second))).isoformat()


def build_products(seed, n):
    """Pure builder: list of `n` semi-structured product documents (dicts).
    Vectorized draws (fixed order P1..P15, see design.md), then per-document
    assembly. No DB, no file I/O."""
    n = max(1, int(n))
    rng = np.random.default_rng(seed)

    category_idx = rng.choice(len(CATEGORIES), size=n, p=category_weights())   # P1
    domain_idx = rng.choice(len(DOMAINS), size=n, p=domain_weights())          # P2
    brand_idx = rng.choice(len(BRANDS), size=n, p=brand_weights())             # P3

    medians = np.array([CATEGORY_PRICE_PROFILE[c][0] for c in CATEGORIES])
    sigmas = np.array([CATEGORY_PRICE_PROFILE[c][1] for c in CATEGORIES])
    z = rng.normal(size=n)                                                     # P4
    price = np.round(np.exp(np.log(medians[category_idx]) + sigmas[category_idx] * z), 2)
    np.clip(price, 0.5, None, out=price)

    currency_idx = rng.choice(len(CURRENCIES), size=n, p=CURRENCY_WEIGHTS)     # P5
    in_stock = rng.random(n) < IN_STOCK_P                                      # P6
    seller_id = rng.integers(1, N_SELLERS + 1, size=n)                         # P7
    seller_rating = np.round(1.0 + rng.random(n) * 4.0, 1)                     # P8
    day = rng.integers(0, WINDOW_DAYS, size=n)                                 # P9
    second = rng.integers(0, 86400, size=n)                                    # P10
    n_tags = rng.integers(0, 5, size=n)                                        # P11 (0..4)
    tag_rand = rng.random((n, N_TAGS))                                         # P12
    spec_presence = rng.random((n, 3))                                        # P13
    spec_value = rng.random((n, 3))                                           # P14
    title_noun_idx = rng.integers(0, len(CATEGORY_NOUNS[CATEGORIES[0]]), size=n)  # P15

    tag_order = np.argsort(tag_rand, axis=1)
    seller_names = _seller_names(seed)

    products = []
    for i in range(n):
        cat = CATEGORIES[category_idx[i]]
        brand = BRANDS[brand_idx[i]]
        domain = DOMAINS[domain_idx[i]]
        pid = i + 1

        k = int(n_tags[i])
        selected = sorted(int(t) for t in tag_order[i, :k])
        tags = [TAGS[t] for t in selected]

        specs = {}
        for slot, field in enumerate(CATEGORY_SPECS[cat]):
            if spec_presence[i, slot] < SPEC_PRESENT_P:
                pool = SPEC_POOLS[field]
                vi = min(int(spec_value[i, slot] * len(pool)), len(pool) - 1)
                specs[field] = pool[vi]

        noun = CATEGORY_NOUNS[cat][int(title_noun_idx[i])]
        sid = int(seller_id[i])

        products.append({
            "product_id": pid,
            "url": f"https://{domain}/p/{pid}",
            "domain": domain,
            "title": f"{brand} {noun}",
            "brand": brand,
            "category": cat,
            "price": float(price[i]),
            "currency": CURRENCIES[currency_idx[i]],
            "in_stock": bool(in_stock[i]),
            "specs": specs,
            "tags": tags,
            "seller": {
                "seller_id": sid,
                "name": seller_names[sid - 1],
                "rating": float(seller_rating[i]),
            },
            "scraped_at": _iso(day[i], second[i]),
        })
    return products


def build_events(seed, n, products):
    """Pure builder: list of `n` scrape-event dicts COUPLED to the catalog.
    Each event scrapes a REAL product from `products`: its `url`, `domain`, and
    `product_id` come straight from that product (so a product always has the
    same url/domain), while `price`/`in_stock`/`scraped_at` are a fresh scrape
    observation (price = a log-jittered draw around the product's catalog
    price, so the latest scraped price differs from the catalog price — that is
    what the capstone materializes).

    ~70% of events scrape a not-yet-seen product (introductions, drawn without
    replacement so distinct scraped products inherit the catalog's category
    mix), the rest re-scrape an already-seen product with a Zipf popularity
    weight (hot products get re-scraped more), yielding a ~30% duplicate-url
    rate. url duplicate <=> product_id duplicate, since a product's url is
    fixed. Vectorized draws (fixed order E1..E6), then per-event assembly. No
    DB, no file I/O."""
    n = max(1, int(n))
    n_products = len(products)
    rng = np.random.default_rng(seed)

    prod_price = np.array([p["price"] for p in products], dtype=np.float64)

    n_unique = min(max(1, round(n * DUP_UNIQUE_FRACTION)), n, n_products)
    n_dup = n - n_unique

    intro_pos = rng.choice(n_products, size=n_unique, replace=False)                # E1 distinct products
    pop_rank = rng.permutation(n_unique) + 1                                        # E2 popularity among them
    pop_weight = 1.0 / pop_rank ** 1.1
    pop_weight = pop_weight / pop_weight.sum()

    dup_pick = rng.choice(n_unique, size=n_dup, p=pop_weight) if n_dup else np.empty(0, dtype=int)  # E3
    all_pos = np.concatenate([intro_pos, intro_pos[dup_pick]])
    all_pos = all_pos[rng.permutation(n)]                                           # E4 stream shuffle

    noise = rng.normal(0.0, EVENT_PRICE_SIGMA, size=n)                              # E5a
    price = np.round(prod_price[all_pos] * np.exp(noise), 2)
    np.clip(price, 0.5, None, out=price)
    in_stock = rng.random(n) < IN_STOCK_P                                           # E5b
    day = rng.integers(0, WINDOW_DAYS, size=n)                                      # E6a
    second = rng.integers(0, 86400, size=n)                                        # E6b

    events = []
    for i in range(n):
        prod = products[int(all_pos[i])]
        events.append({
            "event_id": i + 1,
            "url": prod["url"],
            "domain": prod["domain"],
            "product_id": prod["product_id"],
            "price": float(price[i]),
            "in_stock": bool(in_stock[i]),
            "scraped_at": _iso(day[i], second[i]),
        })
    return events


def _ground_truth(scale, products, events):
    n_products = len(products)
    n_events = len(events)
    n_cat = len(CATEGORIES)
    cat_index = {c: i for i, c in enumerate(CATEGORIES)}

    cat_count = np.zeros(n_cat, dtype=np.int64)
    cat_price = np.zeros(n_cat, dtype=np.float64)
    cat_instock = np.zeros(n_cat, dtype=np.int64)
    brand_count = {}
    price_sum = 0.0
    graded_ids = []
    nested_count = 0

    for p in products:
        ci = cat_index[p["category"]]
        cat_count[ci] += 1
        cat_price[ci] += p["price"]
        if p["in_stock"]:
            cat_instock[ci] += 1
        brand_count[p["brand"]] = brand_count.get(p["brand"], 0) + 1
        price_sum += p["price"]
        if p["category"] == "electronics" and p["in_stock"] and "sale" in p["tags"]:
            graded_ids.append(p["product_id"])
        if p["specs"].get("color") == "black":
            nested_count += 1

    per_category = {}
    for c in CATEGORIES:
        ci = cat_index[c]
        cnt = int(cat_count[ci])
        per_category[c] = {
            "count": cnt,
            "avg_price": round(float(cat_price[ci] / cnt), 2) if cnt else 0.0,
            "in_stock_count": int(cat_instock[ci]),
        }

    top_brands = sorted(brand_count.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    top_brands = [[b, c] for b, c in top_brands]

    # --- events ---
    ev_domain = np.array([e["domain"] for e in events], dtype=object)
    ev_url = np.array([e["url"] for e in events], dtype=object)
    ev_pid = np.array([e["product_id"] for e in events], dtype=np.int64)
    ev_price = np.array([e["price"] for e in events], dtype=np.float64)
    ev_time = np.array(
        [datetime.fromisoformat(e["scraped_at"]).timestamp() for e in events],
        dtype=np.float64,
    )
    ev_id = np.array([e["event_id"] for e in events], dtype=np.int64)

    unique_urls = int(len(set(ev_url.tolist())))
    duplicate_events = n_events - unique_urls

    per_domain = {}
    for d in DOMAINS:
        c = int(np.count_nonzero(ev_domain == d))
        if c:
            per_domain[d] = c

    # latest event per product_id by (scraped_at, event_id)
    order = np.lexsort((ev_id, ev_time))          # ascending; last per pid is latest
    sorted_pid = ev_pid[order]
    sorted_price = ev_price[order]
    rev_pid = sorted_pid[::-1]
    rev_price = sorted_price[::-1]
    uniq_pid, first_idx = np.unique(rev_pid, return_index=True)
    latest_price = rev_price[first_idx]

    pid_to_cat = {p["product_id"]: p["category"] for p in products}
    per_category_count = {c: 0 for c in CATEGORIES}
    for pid in uniq_pid.tolist():
        per_category_count[pid_to_cat[pid]] += 1

    current_state = {
        "count": int(uniq_pid.size),
        "price_sum": round(float(latest_price.sum()), 2),
        "per_category_count": per_category_count,
    }

    return {
        "seed": {"products": SEED_PRODUCTS, "events": SEED_EVENTS},
        "scale": scale,
        "n_products": n_products,
        "n_events": n_events,
        "categories": CATEGORIES,
        "row_counts": {"products": n_products, "events": n_events},
        "per_category": per_category,
        "top_brands": top_brands,
        "graded_query": {
            "category": "electronics",
            "tag": "sale",
            "in_stock": True,
            "count": len(graded_ids),
            "product_ids": sorted(graded_ids),
        },
        "nested_query": {
            "path": "specs.color",
            "value": "black",
            "count": nested_count,
        },
        "price_sum": round(float(price_sum), 2),
        "events": {
            "total": n_events,
            "unique_urls": unique_urls,
            "duplicate_events": duplicate_events,
            "per_domain": per_domain,
        },
        "current_state": current_state,
    }


def _write_ndjson(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def generate():
    scale = float(os.environ.get("SCALE", "1.0"))
    n_events = max(1, round(N_EVENTS_BASE * scale))
    n_products = max(1, round(N_PRODUCTS_BASE * scale))

    print(f"SCALE={scale} n_products={n_products} n_events={n_events}")

    products = build_products(SEED_PRODUCTS, n_products)
    events = build_events(SEED_EVENTS, n_events, products)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _write_ndjson(PRODUCTS_PATH, products)
    _write_ndjson(EVENTS_PATH, events)
    print(f"wrote {PRODUCTS_PATH.name} ({len(products)}) and {EVENTS_PATH.name} ({len(events)})")

    gt = _ground_truth(scale, products, events)
    GROUND_TRUTH_PATH.write_text(json.dumps(gt, indent=2), encoding="utf-8")
    print(f"ground truth written: {GROUND_TRUTH_PATH}")
    print(f"  price_sum={gt['price_sum']} graded_query.count={gt['graded_query']['count']} "
          f"nested_query.count={gt['nested_query']['count']}")
    dup_pct = 100.0 * gt['events']['duplicate_events'] / gt['events']['total']
    print(f"  events unique_urls={gt['events']['unique_urls']} "
          f"duplicate_events={gt['events']['duplicate_events']} ({dup_pct:.1f}%)")
    print(f"  current_state count={gt['current_state']['count']} "
          f"price_sum={gt['current_state']['price_sum']}")


if __name__ == "__main__":
    sys.exit(generate())
