"""Deterministic generator for module 13 (scraping at scale).

Writes THREE files under data/ (all gitignored except ground-truth.json):

    data/catalog.json       the target site's clean canonical product corpus
    data/target-spec.json   the hostile target's defense/behavior config --
                             read by BOTH docker/target/app.py (to actually
                             enforce it) and validators (to build an oracle)
    data/ground-truth.json  COMMITTED answer key, SCALE=1.0

Neither catalog.json nor target-spec.json is a "reference solution" -- they
are the target APP's own backend data (like a real site's product DB and
WAF config), not a task scaffold. They are still not meant for a learner to
open directly while attempting a task built on top of this infra: reading
target-spec.json trivially reveals the rate-limit thresholds, honeypot ids,
and markup-version scheme that recon/resilience tasks ask the learner to
discover through observation. Task READMEs authored in later waves must say
so explicitly (see .authoring/design.md).

Seed 131313 (`harness.common.SEED`). Vectorized numpy throughout every
`build_*` function -- each is PURE (numpy + stdlib only, no file I/O) and
independently seeded, so a validator can synthesize any one piece of the
corpus in-memory without replaying the others' draws first. Exact draw
order is documented in .authoring/design.md -- reordering any rng call
invalidates the committed ground truth.

Respects `SCALE` (env, default 1.0): N_PRODUCTS = 4,000 * SCALE.
`GROUND_TRUTH_ONLY=1` skips writing catalog.json/target-spec.json and only
(re)writes ground-truth.json -- fast, no heavier JSON serialization.

Usage:
    uv run python generate.py                       # SCALE=1.0
    SCALE=0.2 uv run python generate.py              # light local run
    GROUND_TRUTH_ONLY=1 uv run python generate.py    # rewrite answer key only, fast
"""

import json
import os
import re
import sys
from pathlib import Path

import numpy as np

MODULE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    CATALOG_PATH,
    DATA_DIR,
    GROUND_TRUTH_PATH,
    SEED,
    TARGET_SPEC_PATH,
)

SEED_SELLERS = SEED + 1
SEED_PRODUCTS = SEED + 2
SEED_BAD_RECORDS = SEED + 3
SEED_HONEYPOTS = SEED + 4
SEED_CHANGES = SEED + 5

N_PRODUCTS_BASE = 4_000
N_SELLERS_BASE = 140
HONEYPOT_COUNT_BASE = 30
TRAP_TOKENS_COUNT = 5

BAD_FRACTION = 0.10
DEFECT_TYPES = [
    "missing_price", "price_na", "empty_title",
    "negative_price", "bad_currency", "truncated",
]

N_DAYS = 5              # days 0..4; day 0 is the baseline (no changes applied)
CHANGE_FRACTION = 0.04  # ~4% of products change per day, relative to the PREVIOUS day
PRICE_CHANGE_PROB = 0.70  # vs. a stock flip

MARKUP_VERSION_COUNT = 4

HTTP_COST = 1.0
API_EXTRA_COST = 7.0       # additional cost of calling /api/product/{id} beyond the html fetch
RENDER_COST = HTTP_COST + API_EXTRA_COST
COMPLETENESS_TARGET = 0.98

CATEGORIES = [
    "electronics", "home-goods", "books", "toys", "sporting-goods",
    "office-supplies", "beauty", "apparel", "grocery", "automotive",
]

# (median, sigma) for a log-normal price draw per category.
CATEGORY_PRICE_PROFILE = {
    "electronics": (89.0, 0.9), "home-goods": (39.0, 0.7), "books": (14.0, 0.4),
    "toys": (19.0, 0.6), "sporting-goods": (49.0, 0.7), "office-supplies": (12.0, 0.5),
    "beauty": (18.0, 0.5), "apparel": (28.0, 0.6), "grocery": (8.0, 0.4),
    "automotive": (59.0, 0.8),
}

NOUNS = {
    "electronics": ["Headphones", "Bluetooth Speaker", "Power Bank", "Webcam", "Smartwatch", "Router"],
    "home-goods": ["Throw Pillow", "Wall Clock", "Area Rug", "Storage Bin", "Table Lamp", "Curtain Set"],
    "books": ["Novel", "Cookbook", "Field Guide", "Journal", "Anthology", "Textbook"],
    "toys": ["Building Blocks", "Puzzle Set", "Remote Car", "Plush Toy", "Board Game", "Action Figure"],
    "sporting-goods": ["Yoga Mat", "Resistance Bands", "Water Bottle", "Running Shoes", "Dumbbell Set", "Bike Helmet"],
    "office-supplies": ["Notebook Pack", "Desk Organizer", "Stapler", "Sticky Notes", "Pen Set", "Whiteboard"],
    "beauty": ["Face Serum", "Lip Balm Set", "Hair Dryer", "Makeup Brush Set", "Body Lotion", "Nail Kit"],
    "apparel": ["Cotton T-Shirt", "Denim Jacket", "Wool Scarf", "Running Socks", "Baseball Cap", "Rain Jacket"],
    "grocery": ["Coffee Beans", "Pasta Pack", "Olive Oil", "Granola Bars", "Spice Set", "Tea Sampler"],
    "automotive": ["Floor Mats", "Car Charger", "Dash Cam", "Seat Cover Set", "Tire Gauge", "Roof Rack"],
}

ADJECTIVES = ["Premium", "Classic", "Pro", "Essential", "Deluxe",
              "Compact", "Ultra", "Everyday", "Signature", "Basic"]

BRANDS = ["Kestrel", "Orbiton", "Fennwick", "Trueline", "Marlowe", "Cinderpeak", "Voxel",
          "Pinegrove", "Auralite", "Basecamp", "Northfield", "Circuitry", "Sablewood",
          "Loomis", "Verity", "Highmark", "Coastway", "Ironpeak", "Wrenfield", "Lucent"]

SELLER_WORD1 = ["Nova", "Bright", "Urban", "Prime", "Swift", "True", "Everyday", "North",
                "Vital", "Metro", "Silverline", "Golden", "Cedar", "Harbor", "Vertex",
                "Bluewave", "Solstice", "Crown", "Anchor", "Cobalt"]
SELLER_WORD2 = ["Market", "Traders", "Goods", "Supply Co", "Outlet", "Emporium",
                "Bazaar", "Depot", "Collective", "Mercantile", "Exchange", "Warehouse"]

CURRENCIES = ["USD", "EUR", "GBP", "CAD"]
CURRENCY_WEIGHTS = [0.90, 0.05, 0.03, 0.02]

CARRIERS = ["QuickShip", "MetroPost", "CargoLine", "ParcelJet"]
SHIPPING_ETA_CHOICES = np.array([1, 2, 3, 5, 7, 10])
SHIPPING_ETA_WEIGHTS = [0.10, 0.20, 0.25, 0.20, 0.15, 0.10]

DESCRIPTION_FILLERS = [
    "Built for everyday use with a focus on reliability.",
    "A customer favorite, restocked regularly.",
    "Backed by a standard manufacturer warranty.",
    "Designed to balance quality and value.",
    "Ships in eco-friendly, minimal packaging.",
    "Part of this season's curated selection.",
]

# review_count ~ Poisson(REVIEW_LAMBDA); P(count == 0) = exp(-lambda) is tuned so
# ~30% of products have review_count > 0 -- see build_products' docstring and
# .authoring/design.md's cost-model section for why this drives the router split.
REVIEW_LAMBDA = 0.357


def _zipf_weights(k, s=1.1):
    ranks = np.arange(k)
    w = 1.0 / (ranks + 1) ** s
    return w / w.sum()


def _slugify(text, max_len=40):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].rstrip("-")


# --------------------------------------------------------------------------
# Pure builders -- numpy + stdlib only, no file I/O. Independently seeded.
# --------------------------------------------------------------------------

def build_categories():
    """Pure, NO rng: 10 fixed categories, ids 1..10 in CATEGORIES order."""
    return [{"id": i + 1, "name": name} for i, name in enumerate(CATEGORIES)]


def build_sellers(seed, n):
    """Pure: dict of arrays (id, name). Draw order SE1..SE2."""
    n = max(1, int(n))
    rng = np.random.default_rng(seed)
    w1_idx = rng.integers(0, len(SELLER_WORD1), size=n)  # SE1
    w2_idx = rng.integers(0, len(SELLER_WORD2), size=n)  # SE2
    ids = np.arange(1, n + 1)
    names = [f"{SELLER_WORD1[w1_idx[i]]} {SELLER_WORD2[w2_idx[i]]}" for i in range(n)]
    return {"id": ids, "name": names}


def build_products(seed, n, n_sellers, seller_names, categories):
    """Pure: dict of arrays/lists, one entry per product (id 1..n). Draw
    order P1..P14 (P14 runs inside a fixed-order per-category loop, mirroring
    module 12's per-family title loop).

    `review_count` (P7, Poisson(REVIEW_LAMBDA)) is the field that decides
    whether `rating`/`shipping_info` are REQUIRED for a product's
    completeness score: both are always JS-only (never in HTML, any
    product), but they only count as "required" when review_count > 0 (a
    product with zero reviews legitimately has no rating to show). This is
    what makes the budget router's job non-trivial: review_count ITSELF is
    HTML-visible, so a router can decide whether to escalate to
    /api/product/{id} without blindly rendering every product.
    """
    n = max(1, int(n))
    n_cat = len(categories)
    rng = np.random.default_rng(seed)

    cat_pos = rng.choice(n_cat, size=n, p=_zipf_weights(n_cat, 1.1))       # P1
    category_id = np.asarray([c["id"] for c in categories])[cat_pos]

    seller_pop_rank = rng.permutation(n_sellers) + 1                       # P2
    seller_pop_weight = 1.0 / seller_pop_rank ** 1.2
    seller_pop_weight = seller_pop_weight / seller_pop_weight.sum()
    seller_id = rng.choice(np.arange(1, n_sellers + 1), size=n, p=seller_pop_weight)  # P3

    medians = np.array([CATEGORY_PRICE_PROFILE[CATEGORIES[i]][0] for i in range(n_cat)])
    sigmas = np.array([CATEGORY_PRICE_PROFILE[CATEGORIES[i]][1] for i in range(n_cat)])
    z = rng.normal(size=n)                                                 # P4
    price = np.round(np.exp(np.log(medians[cat_pos]) + sigmas[cat_pos] * z), 2)
    np.clip(price, 0.5, None, out=price)

    currency_idx = rng.choice(len(CURRENCIES), size=n, p=CURRENCY_WEIGHTS)  # P5
    in_stock = rng.random(n) < 0.85                                        # P6
    review_count = rng.poisson(REVIEW_LAMBDA, size=n)                      # P7
    rating_z = rng.normal(size=n)                                          # P8
    shipping_free = rng.random(n) < 0.60                                   # P9
    eta_idx = rng.choice(len(SHIPPING_ETA_CHOICES), size=n, p=SHIPPING_ETA_WEIGHTS)  # P10
    carrier_idx = rng.integers(0, len(CARRIERS), size=n)                   # P11
    brand_idx = rng.integers(0, len(BRANDS), size=n)                       # P12
    adj_idx = rng.integers(0, len(ADJECTIVES), size=n)                     # P13
    filler_idx = rng.integers(0, len(DESCRIPTION_FILLERS), size=n)

    rating = np.round(np.clip(4.3 + 0.5 * rating_z, 1.0, 5.0), 1)
    rating = np.where(review_count > 0, rating, np.nan)

    titles = [None] * n
    for ci, cat in enumerate(CATEGORIES):                                  # P14 (per category, fixed order)
        idx = np.where(cat_pos == ci)[0]
        if idx.size == 0:
            continue
        nouns = NOUNS[cat]
        noun_choice = rng.integers(0, len(nouns), size=idx.size)
        for j, pi in enumerate(idx):
            titles[pi] = f"{ADJECTIVES[adj_idx[pi]]} {nouns[noun_choice[j]]}"

    ids = np.arange(1, n + 1)
    category_names = [CATEGORIES[cat_pos[i]] for i in range(n)]
    currencies = [CURRENCIES[currency_idx[i]] for i in range(n)]
    brands = [BRANDS[brand_idx[i]] for i in range(n)]
    carriers = [CARRIERS[carrier_idx[i]] for i in range(n)]
    eta_days = [int(SHIPPING_ETA_CHOICES[eta_idx[i]]) for i in range(n)]
    seller_id_list = [int(x) for x in seller_id]
    seller_name_list = [seller_names[sid - 1] for sid in seller_id_list]
    descriptions = [
        f"{titles[i]} by {brands[i]}. {DESCRIPTION_FILLERS[filler_idx[i]]}" for i in range(n)
    ]
    slugs = [f"{_slugify(titles[i])}-{ids[i]}" for i in range(n)]

    return {
        "id": ids, "slug": slugs, "url": [f"/product/{i}" for i in ids],
        "title": titles, "category": category_names, "brand": brands,
        "price": price, "currency": currencies, "in_stock": in_stock,
        "seller_id": seller_id_list, "seller_name": seller_name_list,
        "review_count": review_count, "rating": rating,
        "shipping_free": shipping_free, "shipping_eta_days": eta_days,
        "shipping_carrier": carriers, "description": descriptions,
    }


def build_bad_records(seed, product_ids, fraction=BAD_FRACTION, defect_types=None):
    """Pure: dict {product_id (int): defect_type (str)}. Chooses a
    deterministic subset (no replacement) and splits it as evenly as
    possible across `defect_types` in shuffled order."""
    defect_types = defect_types or DEFECT_TYPES
    rng = np.random.default_rng(seed)
    product_ids = np.asarray(product_ids)
    n_bad = max(1, round(fraction * len(product_ids)))
    chosen = rng.choice(product_ids, size=n_bad, replace=False)
    rng.shuffle(chosen)
    buckets = np.array_split(chosen, len(defect_types))
    result = {}
    for defect, ids in zip(defect_types, buckets):
        for pid in ids:
            result[int(pid)] = defect
    return result


def build_honeypots(seed, n_products, count=HONEYPOT_COUNT_BASE, n_trap_tokens=TRAP_TOKENS_COUNT):
    """Pure: {"product_ids": [...], "trap_tokens": [...]}. Honeypot product
    ids are a contiguous block immediately ABOVE the real 1..n_products
    range, so a validator can classify "is this id a honeypot" with a single
    range check with no lookup table needed. Trap tokens are random hex
    slugs for the separate /trap/{token} vector."""
    rng = np.random.default_rng(seed)
    count = max(1, int(count))
    product_ids = list(range(n_products + 1, n_products + 1 + count))
    hex_digits = rng.integers(0, 16, size=(n_trap_tokens, 8))
    trap_tokens = ["".join(f"{d:x}" for d in row) for row in hex_digits]
    return {"product_ids": product_ids, "trap_tokens": trap_tokens}


def build_change_days(seed, product_ids, baseline_price, baseline_in_stock,
                       n_days=N_DAYS, fraction=CHANGE_FRACTION):
    """Pure: dict {day (int, 1..n_days-1): {product_id: {"price": x} or
    {"in_stock": bool}}}. Each day is drawn with its OWN seed (seed + day)
    so a validator can recompute a single day's change set without replaying
    earlier days -- but the recorded NEW VALUES are cumulative (a day's
    change is relative to the PREVIOUS day's effective state, matching what
    a real day-over-day price-tracking target would do), so this function
    still walks days 1..n_days-1 in order internally to track running state."""
    product_ids = np.asarray(product_ids)
    n = len(product_ids)
    running_price = np.array(baseline_price, dtype=float, copy=True)
    running_stock = np.array(baseline_in_stock, dtype=bool, copy=True)
    id_to_pos = {int(pid): i for i, pid in enumerate(product_ids)}

    days = {}
    n_change = max(1, round(fraction * n))
    for d in range(1, n_days):
        rng = np.random.default_rng(seed + d)
        chosen = rng.choice(product_ids, size=n_change, replace=False)
        is_price_change = rng.random(n_change) < PRICE_CHANGE_PROB
        factors = rng.uniform(0.85, 1.20, size=n_change)
        day_changes = {}
        for k, pid in enumerate(chosen):
            pos = id_to_pos[int(pid)]
            if is_price_change[k]:
                new_price = round(float(running_price[pos]) * float(factors[k]), 2)
                running_price[pos] = new_price
                day_changes[int(pid)] = {"price": new_price}
            else:
                new_stock = not bool(running_stock[pos])
                running_stock[pos] = new_stock
                day_changes[int(pid)] = {"in_stock": new_stock}
        days[d] = day_changes
    return days


def build_markup_versions():
    """Pure, NO rng: metadata describing the K=4 detail-page encodings.
    `docker/target/app.py` implements the actual rendering; this is the
    documented contract both the app and validators/task authors read.
    Default (no ?v= given, chaos disabled) version assignment is a fixed
    per-product formula: 1 + (product_id % count)."""
    return {
        "count": MARKUP_VERSION_COUNT,
        "default_assignment": "1 + (product_id % count)",
        "versions": {
            "1": {
                "name": "classic-div",
                "encoding": "plain div/span structure with descriptive class "
                            "names (.product-title, .price, .stock, .reviews); "
                            "price as visible text 'CURRENCY AMOUNT'.",
            },
            "2": {
                "name": "microdata",
                "encoding": "schema.org Product microdata (itemprop attributes); "
                            "price duplicated as a <meta itemprop=price content=...> "
                            "AND a separate visible '.display-price' span in a "
                            "DIFFERENT order (amount before currency).",
            },
            "3": {
                "name": "jsonld",
                "encoding": "price and currency exist ONLY inside a "
                            "<script type=application/ld+json> schema.org Product "
                            "block -- no visible price text anywhere else on the page.",
            },
            "4": {
                "name": "data-island",
                "encoding": "minimal semantic HTML shell; price/currency/"
                            "in_stock/seller live only inside "
                            "<script id=__DATA__ type=application/json>, "
                            "mimicking a client-side-rendered SPA shell.",
            },
        },
    }


def build_cost_model(n_products, review_count, http_cost=HTTP_COST,
                      api_extra_cost=API_EXTRA_COST, completeness_target=COMPLETENESS_TARGET):
    """Pure: the modeled (NOT wall-clock) cost/completeness figures for the
    three task-05 strategies. `render_cost` is what a single "headless
    render" of one product costs (the html fetch PLUS the api fetch); the
    mixed router only pays that api_extra_cost for products that actually
    need it (review_count > 0)."""
    requires_detail_count = int(np.count_nonzero(np.asarray(review_count) > 0))
    fraction = requires_detail_count / n_products
    render_cost = http_cost + api_extra_cost
    return {
        "http_cost": http_cost,
        "api_extra_cost": api_extra_cost,
        "render_cost": render_cost,
        "completeness_target": completeness_target,
        "requires_detail_count": requires_detail_count,
        "requires_detail_fraction": round(fraction, 4),
        "all_http_completeness": round(1.0 - fraction, 4),
        "all_render_completeness": 1.0,
        "mixed_completeness": 1.0,
        "all_http_cost": round(n_products * http_cost, 2),
        "all_render_cost": round(n_products * render_cost, 2),
        "mixed_cost": round(n_products * http_cost + requires_detail_count * api_extra_cost, 2),
    }


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def _catalog_dict(scale, categories, sellers, products):
    n = len(products["id"])
    rows = []
    for i in range(n):
        rating = products["rating"][i]
        rows.append({
            "id": int(products["id"][i]),
            "slug": products["slug"][i],
            "url": products["url"][i],
            "title": products["title"][i],
            "category": products["category"][i],
            "brand": products["brand"][i],
            "price": float(products["price"][i]),
            "currency": products["currency"][i],
            "in_stock": bool(products["in_stock"][i]),
            "seller_id": products["seller_id"][i],
            "seller_name": products["seller_name"][i],
            "review_count": int(products["review_count"][i]),
            "rating": None if np.isnan(rating) else float(rating),
            "shipping_free": bool(products["shipping_free"][i]),
            "shipping_eta_days": products["shipping_eta_days"][i],
            "shipping_carrier": products["shipping_carrier"][i],
            "description": products["description"][i],
        })
    return {
        "seed": SEED, "scale": scale,
        "n_products": n, "n_sellers": len(sellers["id"]),
        "categories": categories,
        "sellers": [{"id": int(sellers["id"][i]), "name": sellers["name"][i]} for i in range(len(sellers["id"]))],
        "products": rows,
    }


def _target_spec_dict(scale, n_products, bad_map, honeypots, change_days, cost_model):
    return {
        "seed": SEED, "scale": scale,
        "required_headers": {
            "user_agent_substring": "Mozilla/5.0",
            "accept_language_required": True,
            "note": "Missing/non-matching User-Agent OR a missing/empty "
                    "Accept-Language header -> 403 on every non-debug route. "
                    "This is the header/behavioral 'client fingerprint' "
                    "defense; real TLS/JA3 fingerprinting is out of scope "
                    "(see design.md).",
        },
        "rate_limit": {
            "capacity": 25,
            "refill_per_sec": 50.0,
            "ban_after_violations": 25,
            "note": "Token bucket per X-Client-Id (or a per-connection "
                    "fallback id if the header is absent). A request without "
                    "a token gets 429 and counts as one violation. "
                    "ban_after_violations is CUMULATIVE 429 count, not a "
                    "rolling window -- once a client crosses it, banned=True "
                    "and every further request gets 403 (until /__debug/reset). "
                    "Tuned so a BOUNDED-concurrency polite crawler (~8-16 "
                    "concurrent, or a modest fixed delay) sustains ~50-80 "
                    "req/s with ~0 violations -- a full 4000-product sweep "
                    "in roughly a minute -- while an UNBOUNDED-concurrency "
                    "burst (asyncio.gather over hundreds of ids at once) "
                    "instantly exhausts the capacity=25 burst budget and "
                    "crosses the ban threshold. The BURST/CONCURRENCY gate "
                    "(capacity), not the sustained rate, is what is meant to "
                    "catch a naive scraper.",
        },
        "honeypots": {
            "product_ids": honeypots["product_ids"],
            "trap_tokens": honeypots["trap_tokens"],
            "trap_path_prefix": "/trap/",
            "note": "Honeypot product ids render a convincing decoy detail "
                    "page but are NEVER linked from a real product page -- "
                    "only from hidden markup in /catalog listings (display:none "
                    "/ class=hp / rel=nofollow). Any GET on a honeypot product "
                    "id, or any /trap/* path, flags honeypot_hits and bans "
                    "immediately (no violation threshold).",
        },
        "markup_versions": build_markup_versions(),
        "js_only_fields": ["rating", "shipping_info"],
        "requires_detail_rule": "rating/shipping_info are REQUIRED fields for "
                                 "completeness only when review_count > 0; "
                                 "review_count itself is HTML-visible.",
        "bad_records": {
            "fraction": BAD_FRACTION,
            "total": len(bad_map),
            "defect_types": DEFECT_TYPES,
            "by_id": {str(k): v for k, v in sorted(bad_map.items())},
        },
        "change_days": {
            "n_days": N_DAYS,
            "change_fraction": CHANGE_FRACTION,
            "days": {str(d): {str(pid): v for pid, v in changes.items()} for d, changes in change_days.items()},
        },
        "cost_model": cost_model,
        "nonce": {
            "html_tag": '<meta name="x-nonce" content="...">',
            "json_key": "_nonce",
            "note": "A fresh random value on EVERY response, html or json, "
                    "unrelated to `day`/`v`. Unchanged pages must be "
                    "byte-stable across requests EXCEPT this field -- "
                    "fingerprints (task 03) must exclude it.",
        },
        "chaos": {
            "enabled_via": "?chaos=1 query param (per-request) or TARGET_CHAOS=1 env (server-wide)",
            "period_sec": 30,
            "note": "When enabled, markup version cycles by wall-clock "
                    "instead of the steady per-product default. ?v= always "
                    "wins over both steady default and chaos.",
        },
    }


def _ground_truth(scale, n_products, categories, products, bad_map, honeypots, change_days, cost_model):
    price = products["price"]
    cat_names = products["category"]
    per_category_counts = {c["name"]: int(sum(1 for x in cat_names if x == c["name"])) for c in categories}

    by_defect = {d: [] for d in DEFECT_TYPES}
    for pid, defect in bad_map.items():
        by_defect[defect].append(pid)
    for d in by_defect:
        by_defect[d].sort()

    return {
        "seed": SEED, "scale": scale,
        "n_products": n_products,
        "price_sum": round(float(price.sum()), 2),
        "per_category_counts": per_category_counts,
        "js_only_fields": ["rating", "shipping_info"],
        "honeypot_ids": honeypots["product_ids"],
        "trap_tokens": honeypots["trap_tokens"],
        "bad_records": {"total": len(bad_map), "by_defect": by_defect},
        "markup_version_count": MARKUP_VERSION_COUNT,
        "change_days": {str(d): sorted(changes.keys()) for d, changes in change_days.items()},
        "cost_model": cost_model,
    }


def generate():
    scale = float(os.environ.get("SCALE", "1.0"))
    ground_truth_only = os.environ.get("GROUND_TRUTH_ONLY", "") not in ("", "0", "false")

    n_products = max(50, int(round(N_PRODUCTS_BASE * scale)))
    n_sellers = max(5, int(round(N_SELLERS_BASE * scale)))
    honeypot_count = max(5, int(round(HONEYPOT_COUNT_BASE * scale)))

    print(f"SCALE={scale} GROUND_TRUTH_ONLY={ground_truth_only} "
          f"n_products={n_products} n_sellers={n_sellers} honeypot_count={honeypot_count}")

    categories = build_categories()
    sellers = build_sellers(SEED_SELLERS, n_sellers)
    products = build_products(SEED_PRODUCTS, n_products, n_sellers, sellers["name"], categories)
    bad_map = build_bad_records(SEED_BAD_RECORDS, products["id"])
    honeypots = build_honeypots(SEED_HONEYPOTS, n_products, honeypot_count)
    change_days = build_change_days(SEED_CHANGES, products["id"], products["price"], products["in_stock"])
    cost_model = build_cost_model(n_products, products["review_count"])

    print(f"built: products={n_products} sellers={n_sellers} "
          f"bad_records={len(bad_map)} honeypots={len(honeypots['product_ids'])}")

    gt = _ground_truth(scale, n_products, categories, products, bad_map, honeypots, change_days, cost_model)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_PATH.write_text(json.dumps(gt, indent=2), encoding="utf-8")
    print(f"ground truth written: {GROUND_TRUTH_PATH}")
    print(f"  price_sum={gt['price_sum']} bad_records_total={gt['bad_records']['total']} "
          f"honeypots={len(gt['honeypot_ids'])} markup_versions={gt['markup_version_count']}")
    print(f"  cost_model={cost_model}")

    if ground_truth_only:
        print("GROUND_TRUTH_ONLY: skipped catalog.json/target-spec.json")
        return

    catalog = _catalog_dict(scale, categories, sellers, products)
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(f"catalog written: {CATALOG_PATH} ({len(catalog['products'])} products)")

    spec = _target_spec_dict(scale, n_products, bad_map, honeypots, change_days, cost_model)
    TARGET_SPEC_PATH.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"target spec written: {TARGET_SPEC_PATH}")


if __name__ == "__main__":
    sys.exit(generate())
