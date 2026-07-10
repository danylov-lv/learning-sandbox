"""Deterministic generator of the scraped price-update event stream for module 07.

Writes data/events.ndjson (one JSON event per line, in publish/seq order) and
data/ground-truth.json (the committed answer key). See .authoring/design.md for
the full data contract — this file must stay in sync with it.

Respects SCALE (default 1.0) for volume. Deterministic: a single seeded
np.random.default_rng(70707) stream, so the same SCALE always reproduces the
same corpus. Draw order is fixed and documented in design.md.

Usage:
    uv run python generate.py
    SCALE=0.05 uv run python generate.py
"""

import json
import math
import os
import sys
from pathlib import Path

import numpy as np

SEED = 70707
MODULE_ROOT = Path(__file__).resolve().parent
EVENTS_PATH = MODULE_ROOT / "data" / "events.ndjson"
GROUND_TRUTH_PATH = MODULE_ROOT / "data" / "ground-truth.json"

N_PRODUCTS = 5000
BASE_EVENTS = 200_000
LATE_RATE = 0.02
IN_STOCK_P = 0.85
RECOMMENDED_PARTITIONS = 6

WINDOW_START_ISO = "2025-07-01T00:00:00Z"
WINDOW_END_ISO = "2025-07-01T02:00:00Z"
WINDOW_MS = 2 * 60 * 60 * 1000  # 2 hours
TUMBLE_MS = 15 * 60 * 1000      # 15-minute tumbling windows
N_WINDOWS = WINDOW_MS // TUMBLE_MS

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

SOURCES = [
    "shopnest.example",
    "dealbarn.example",
    "cartify.example",
    "brightbuy.example",
    "thriftloop.example",
    "primemart.example",
]

CURRENCIES = ["USD", "EUR", "GBP"]
CURRENCY_WEIGHTS = [0.60, 0.25, 0.15]


def category_weights():
    ranks = np.arange(len(CATEGORIES))
    w = 1.0 / (ranks + 1) ** 1.1
    return w / w.sum()


def fmt_ts(ms):
    s, msec = divmod(int(ms), 1000)
    m, sec = divmod(s, 60)
    h, minute = divmod(m, 60)
    return f"2025-07-01T{h:02d}:{minute:02d}:{sec:02d}.{msec:03d}Z"


def fmt_window_start(ms):
    s = int(ms) // 1000
    m, sec = divmod(s, 60)
    h, minute = divmod(m, 60)
    return f"2025-07-01T{h:02d}:{minute:02d}:{sec:02d}Z"


def generate():
    scale = float(os.environ.get("SCALE", "1.0"))
    rng = np.random.default_rng(SEED)
    E = int(round(BASE_EVENTS * scale))

    print(f"SCALE={scale} E={E}")

    # --- Universe (draw order: category assignment, then popularity ranks) ---
    cat_w = category_weights()
    product_category_idx = rng.choice(len(CATEGORIES), size=N_PRODUCTS, p=cat_w)
    popularity_rank = rng.permutation(N_PRODUCTS) + 1
    pop_weight = 1.0 / popularity_rank ** 1.2
    pop_weight = pop_weight / pop_weight.sum()

    # --- Stream (draw order: timestamps, products, sources, currencies,
    #     in_stock, prices per category, then late-event selection) ---
    ts_ms = np.sort(rng.integers(0, WINDOW_MS, size=E))          # ascending event-time
    product_ids = rng.choice(np.arange(1, N_PRODUCTS + 1), size=E, p=pop_weight)
    cats_idx = product_category_idx[product_ids - 1]
    source_idx = rng.integers(0, len(SOURCES), size=E)
    currency_idx = rng.choice(len(CURRENCIES), size=E, p=CURRENCY_WEIGHTS)
    in_stock = rng.random(E) < IN_STOCK_P

    prices = np.zeros(E)
    for ci, cat in enumerate(CATEGORIES):
        mask = cats_idx == ci
        cnt = int(mask.sum())
        if cnt:
            median, sigma = CATEGORY_PRICE_PROFILE[cat]
            prices[mask] = rng.lognormal(math.log(median), sigma, size=cnt)
    prices = np.round(prices, 2)

    late_count = int(round(E * LATE_RATE))
    adj_ms = ts_ms.copy()
    if late_count > 0:
        late_idx = rng.choice(E, size=late_count, replace=False)
        reduce_min = rng.integers(1, 16, size=late_count)       # 1..15 minutes
        adj_ms[late_idx] = np.maximum(0, ts_ms[late_idx] - reduce_min * 60_000)

    # --- Write events.ndjson in seq order (seq == array index) ---
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for i in range(E):
        rec = {
            "event_id": i,
            "seq": i,
            "product_id": int(product_ids[i]),
            "category": CATEGORIES[int(cats_idx[i])],
            "source_site": SOURCES[int(source_idx[i])],
            "price": float(prices[i]),
            "currency": CURRENCIES[int(currency_idx[i])],
            "in_stock": bool(in_stock[i]),
            "event_ts": fmt_ts(adj_ms[i]),
        }
        lines.append(json.dumps(rec, ensure_ascii=False))
    EVENTS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    # --- Ground truth ---
    price_sum_all = round(float(prices.sum()), 2)

    per_category_totals = {}
    for ci, cat in enumerate(CATEGORIES):
        mask = cats_idx == ci
        per_category_totals[cat] = {
            "count": int(mask.sum()),
            "price_sum": round(float(prices[mask].sum()), 2),
        }

    window_idx = np.clip(adj_ms // TUMBLE_MS, 0, N_WINDOWS - 1)
    windows = []
    window_category_agg = {}
    for wi in range(N_WINDOWS):
        start_ms = wi * TUMBLE_MS
        windows.append({
            "start": fmt_window_start(start_ms),
            "end": fmt_window_start(start_ms + TUMBLE_MS),
        })
        wmask = window_idx == wi
        agg = {}
        for ci, cat in enumerate(CATEGORIES):
            cmask = wmask & (cats_idx == ci)
            cnt = int(cmask.sum())
            if cnt:
                agg[cat] = {"count": cnt, "price_sum": round(float(prices[cmask].sum()), 2)}
        window_category_agg[fmt_window_start(start_ms)] = agg

    # latest_state: last event per product in publish (seq) order.
    seq = np.arange(E)
    last_seq = np.full(N_PRODUCTS + 1, -1, dtype=np.int64)
    np.maximum.at(last_seq, product_ids, seq)
    present = np.where(last_seq >= 0)[0]
    latest_price_sum = round(float(prices[last_seq[present]].sum()), 2)

    counts = np.bincount(product_ids, minlength=N_PRODUCTS + 1)
    order = sorted(present.tolist(), key=lambda p: (-int(counts[p]), p))
    top20 = order[:20]
    sample = {}
    for pid in top20:
        s = int(last_seq[pid])
        sample[str(pid)] = {
            "price": float(prices[s]),
            "currency": CURRENCIES[int(currency_idx[s])],
            "in_stock": bool(in_stock[s]),
            "event_ts": fmt_ts(adj_ms[s]),
            "seq": s,
        }

    distinct_products = int(present.size)
    ground_truth = {
        "seed": SEED,
        "scale": scale,
        "event_window": {"start": WINDOW_START_ISO, "end": WINDOW_END_ISO},
        "total_events": E,
        "late_events": late_count,
        "n_products": N_PRODUCTS,
        "distinct_products_with_events": distinct_products,
        "recommended_partitions": RECOMMENDED_PARTITIONS,
        "constants": {
            "categories": CATEGORIES,
            "sources": SOURCES,
            "currency_weights": dict(zip(CURRENCIES, CURRENCY_WEIGHTS)),
        },
        "price_sum_all": price_sum_all,
        "per_category_totals": per_category_totals,
        "windows": windows,
        "window_category_agg": window_category_agg,
        "latest_state": {
            "count": distinct_products,
            "price_sum": latest_price_sum,
            "sample": sample,
        },
    }
    GROUND_TRUTH_PATH.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    print(f"events written: {EVENTS_PATH} ({E} lines)")
    print(f"ground truth written: {GROUND_TRUTH_PATH}")
    print(f"  late_events={late_count} distinct_products={distinct_products}")
    print(f"  price_sum_all={price_sum_all} latest_state.price_sum={latest_price_sum}")


if __name__ == "__main__":
    sys.exit(generate())
