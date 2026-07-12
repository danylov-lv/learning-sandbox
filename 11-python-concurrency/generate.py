"""Deterministic generator for module 11 (Python concurrency: asyncio
event-loop internals).

Builds the capstone's page corpus — a set of "product pages" the mock peer
(`harness/peer.py`) serves and the capstone's bounded async scraping pipeline
crawls — and writes it plus a committed ground-truth aggregate. There is no
docker stack for this module: everything here is a pure in-memory build, no
DB, no network.

  * data/corpus.json     — GITIGNORED. One JSON object mapping URL path
    ("/p/{i}") to a page record `{product_id, category, price}`. Fed to
    `mock_peer(corpus=...)` so the peer can serve realistic bodies, and to
    the capstone validator as the crawl target set.
  * data/ground-truth.json — COMMITTED. The answer key the capstone grades
    its materialized result against: `{seed, scale, n_pages, categories,
    count, price_sum, per_category_count}`, computed by iterating the built
    corpus (never hand-computed / hardcoded).

`build_corpus(seed, n)` is PURE (numpy only, no file I/O) and returns the
same `dict[path, record]` this script writes, so a validator can synthesize
the corpus in-memory without reading `data/corpus.json` (mirrors module 10's
`build_products` / `build_events`).

Deterministic: fixed seed 111111, fixed draw order (see .authoring/design.md
— do not reorder without regenerating and updating every consumer). Respects
`SCALE` (env, default 1.0): `n_pages = round(3000 * SCALE)`.

Usage:
    uv run python generate.py                # SCALE=1.0 (3000 pages)
    SCALE=0.1 uv run python generate.py       # light run
"""

import json
import os
import sys
from pathlib import Path

import numpy as np

MODULE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import DATA_DIR, GROUND_TRUTH_PATH  # noqa: E402

SEED = 111111
N_PAGES_BASE = 3000

CORPUS_PATH = DATA_DIR / "corpus.json"

CATEGORIES = [
    "electronics", "home-goods", "kitchen", "toys", "sporting-goods", "apparel",
]

# (median, sigma) for a log-normal price draw per category.
CATEGORY_PRICE_PROFILE = {
    "electronics": (120.0, 0.9),
    "home-goods": (45.0, 0.7),
    "kitchen": (35.0, 0.6),
    "toys": (25.0, 0.6),
    "sporting-goods": (55.0, 0.7),
    "apparel": (30.0, 0.6),
}


def _zipf_weights(k, s=1.1):
    ranks = np.arange(k)
    w = 1.0 / (ranks + 1) ** s
    return w / w.sum()


def category_weights():
    return _zipf_weights(len(CATEGORIES), 1.1)


def build_corpus(seed, n):
    """Pure builder: dict mapping URL path "/p/{i}" (1-based i) to a page
    record `{product_id, category, price}`. Draw order (fixed, do not
    reorder): G1 category (Zipf over CATEGORIES), G2 price (log-normal,
    per-category median/sigma, round-2, clipped >= 0.5). No DB, no file I/O.
    """
    n = max(1, int(n))
    rng = np.random.default_rng(seed)

    category_idx = rng.choice(len(CATEGORIES), size=n, p=category_weights())  # G1
    medians = np.array([CATEGORY_PRICE_PROFILE[c][0] for c in CATEGORIES])
    sigmas = np.array([CATEGORY_PRICE_PROFILE[c][1] for c in CATEGORIES])
    z = rng.normal(size=n)                                                    # G2
    price = np.round(np.exp(np.log(medians[category_idx]) + sigmas[category_idx] * z), 2)
    np.clip(price, 0.5, None, out=price)

    corpus = {}
    for i in range(n):
        pid = i + 1
        cat = CATEGORIES[category_idx[i]]
        corpus[f"/p/{pid}"] = {
            "product_id": pid,
            "category": cat,
            "price": float(price[i]),
        }
    return corpus


def _ground_truth(corpus, seed, scale):
    per_category_count = {c: 0 for c in CATEGORIES}
    price_sum = 0.0
    for rec in corpus.values():
        per_category_count[rec["category"]] += 1
        price_sum += rec["price"]

    return {
        "seed": seed,
        "scale": scale,
        "n_pages": len(corpus),
        "categories": CATEGORIES,
        "count": len(corpus),
        "price_sum": round(price_sum, 2),
        "per_category_count": per_category_count,
    }


def generate():
    scale = float(os.environ.get("SCALE", "1.0"))
    n_pages = max(1, round(N_PAGES_BASE * scale))

    print(f"SCALE={scale} n_pages={n_pages}")

    corpus = build_corpus(SEED, n_pages)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_PATH.write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {CORPUS_PATH.name} ({len(corpus)} pages)")

    gt = _ground_truth(corpus, SEED, scale)
    GROUND_TRUTH_PATH.write_text(json.dumps(gt, indent=2), encoding="utf-8")
    print(f"ground truth written: {GROUND_TRUTH_PATH}")
    print(f"  n_pages={gt['n_pages']} price_sum={gt['price_sum']}")
    print(f"  per_category_count={gt['per_category_count']}")


if __name__ == "__main__":
    sys.exit(generate())
