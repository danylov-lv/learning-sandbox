"""Deterministic generator for module 15 (LLMs in pipelines).

Builds the shared inputs for tasks 02-06: a canonical product catalog (the
source of truth every derived set is built from), a set of selector-hostile
HTML snippets for structured-extraction, a diluted-signal record set for
classification/enrichment, a title-variant set for embedding dedup, and a
small synthetic "Sandbox Handbook" corpus + QA pairs for mini-RAG.

  * data/ground-truth.json  — COMMITTED. Summary counts + data_sha, computed
    by aggregating the built objects (never hand-computed).
  * data/extraction.json, data/classification.json, data/dedup.json —
    GITIGNORED. Task-facing inputs, gold fields stripped (the pure builders
    below return the full objects WITH gold inline; validators call the
    builders directly to reconstruct gold in-memory, mirroring module 14's
    build_observations()/labels pattern — the on-disk files are never the
    source of gold).
  * data/corpus/<doc_id>.md — GITIGNORED. Full handbook doc text (not gold,
    it's the RAG source material itself).

Every `build_*` function is PURE (numpy + stdlib only, no file I/O) and
takes `seed` (build_catalog also takes `scale`). All are called with the
same SEED = 151515; each opens its own `np.random.default_rng(seed)`, so
independent builders draw independent streams even though they share a
seed value.

`build_extraction_set` / `build_classification_set` / `build_dedup_set`
always draw from the SCALE=1.0 catalog regardless of the module's SCALE
env — they're LLM-call-bound eval sets (every item costs a live model
call to grade), so their size is fixed rather than scaling with SCALE.
Only `build_catalog`'s own size scales.

Usage:
    uv run python generate.py                # SCALE=1.0
    SCALE=0.5 uv run python generate.py       # smaller catalog only
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

MODULE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import CORPUS_DIR, DATA_DIR, GROUND_TRUTH_PATH  # noqa: E402

SEED = 151515

CATEGORIES = [
    "electronics", "home-goods", "kitchen", "toys", "sporting-goods", "apparel", "books", "garden",
]

# (median, sigma) for a log-normal price draw per category.
CATEGORY_PRICE_PROFILE = {
    "electronics": (120.0, 0.80),
    "home-goods": (40.0, 0.60),
    "kitchen": (30.0, 0.50),
    "toys": (18.0, 0.45),
    "sporting-goods": (50.0, 0.65),
    "apparel": (25.0, 0.45),
    "books": (12.0, 0.30),
    "garden": (32.0, 0.55),
}

# 4 brand tokens + 6 (hyphenated, single-token) noun tokens per category, so
# names split on whitespace always yield exactly [brand, adj, noun, model] —
# the dedup builder's distortions rely on this.
CATEGORY_TOKENS = {
    "electronics": {
        "brands": ["Voltix", "Nexara", "Photron", "Quantek"],
        "nouns": ["earbuds", "monitor", "router", "soundbar", "webcam", "power-bank"],
    },
    "home-goods": {
        "brands": ["Hearthly", "Domora", "Linenfolk", "Cozyma"],
        "nouns": ["lamp", "rug", "curtain-set", "throw-pillow", "wall-clock", "candle-jar"],
    },
    "kitchen": {
        "brands": ["Cookaro", "Panvista", "Brewline", "Choppex"],
        "nouns": ["blender", "skillet", "kettle", "cutting-board", "stand-mixer", "thermos"],
    },
    "toys": {
        "brands": ["Funkerie", "Playbrick", "Wondera", "Tumblex"],
        "nouns": ["building-set", "plush-bear", "puzzle", "action-figure", "toy-car", "drone-toy"],
    },
    "sporting-goods": {
        "brands": ["Trailforge", "Pacefit", "Ironclad", "Summitgear"],
        "nouns": ["yoga-mat", "dumbbell-set", "running-shoes", "bike-helmet", "camp-tent", "water-bottle"],
    },
    "apparel": {
        "brands": ["Threadloom", "Urbanwear", "Cottona", "Fibrance"],
        "nouns": ["hoodie", "t-shirt", "denim-jacket", "wind-jacket", "ankle-socks", "wool-scarf"],
    },
    "books": {
        "brands": ["Pageforge", "Inkwell", "Storybound", "Chapterhouse"],
        "nouns": ["novel", "cookbook", "field-guide", "biography", "atlas", "journal"],
    },
    "garden": {
        "brands": ["Greenhold", "Bloomcraft", "Soilwise", "Rootline"],
        "nouns": ["planter", "garden-hose", "pruning-shears", "trellis", "fertilizer-mix", "wheelbarrow"],
    },
}

ADJECTIVES = [
    "Compact", "Premium", "Deluxe", "Classic", "Pro", "Eco", "Portable", "Heavy-Duty", "Slim", "Rustic",
]

# Shared across all categories -- a "generic brand" pool that dilutes brand
# as a perfect category signal in the classification set.
GENERIC_BRANDS = ["Zenmark", "Corebase", "Vantay", "Northlane"]
GENERIC_BRAND_FRAC = 0.30
CROSS_NOUN_NOISE_FRAC = 0.25

COLORS = ["black", "white", "silver", "graphite", "navy", "sand", "forest-green", "slate"]
MATERIALS = ["plastic", "aluminum", "stainless-steel", "cotton", "oak", "silicone", "canvas", "ceramic"]

CATEGORY_ACTIVITY = {
    "electronics": "gadget", "home-goods": "home-decor", "kitchen": "home-cooking", "toys": "collector",
    "sporting-goods": "outdoor", "apparel": "streetwear", "books": "book-club", "garden": "gardening",
}

DESC_TEMPLATES = [
    "A {adj} option that shoppers keep coming back to.",
    "Built for everyday use, {adj} in feel and finish.",
    "One of the {adj} picks in this year's lineup.",
    "Reviewers call it surprisingly {adj} for the price.",
    "A solid choice if you want something {adj} and reliable.",
    "Comes highly rated for its {adj} design.",
    "Popular with shoppers looking for a {adj} upgrade.",
    "Ships fast and holds up well over time.",
]

ABBR_MAP = {
    "Compact": "Cpt", "Premium": "Prem", "Deluxe": "Dlx", "Classic": "Cls", "Pro": "Pro",
    "Eco": "Eco", "Portable": "Port.", "Heavy-Duty": "HD", "Slim": "Slim", "Rustic": "Rstc",
}


def _zipf_weights(k, s=1.1):
    ranks = np.arange(k)
    w = 1.0 / (ranks + 1) ** s
    return w / w.sum()


# --------------------------------------------------------------------------
# build_catalog — canonical products, the source of truth for everything else
# --------------------------------------------------------------------------

def build_catalog(seed, scale):
    """PURE builder: list[dict], one entry per canonical product.

    Draw order (fixed):
      C1 category assignment  — round-robin over CATEGORIES, no rng draw
      C2 brand_idx, adj_idx, noun_idx, model_num, model_letter_idx
      C3 price z-score (log-normal per category)
      C4 color_idx, material_idx, weight_kg, warranty_years
      C5 in_stock
    """
    n = max(1, round(120 * scale))
    n_cat = len(CATEGORIES)
    rng = np.random.default_rng(seed)

    cat_idx = np.arange(n) % n_cat  # C1: deterministic round-robin, no draw

    brand_idx = rng.integers(0, 4, size=n)
    adj_idx = rng.integers(0, len(ADJECTIVES), size=n)
    noun_idx = rng.integers(0, 6, size=n)
    model_num = rng.integers(100, 999, size=n)
    model_letter_idx = rng.integers(0, 26, size=n)

    medians = np.array([CATEGORY_PRICE_PROFILE[c][0] for c in CATEGORIES])
    sigmas = np.array([CATEGORY_PRICE_PROFILE[c][1] for c in CATEGORIES])
    z = rng.normal(size=n)
    price = np.round(np.exp(np.log(medians[cat_idx]) + sigmas[cat_idx] * z), 2)
    np.clip(price, 1.0, None, out=price)

    color_idx = rng.integers(0, len(COLORS), size=n)
    material_idx = rng.integers(0, len(MATERIALS), size=n)
    weight_kg = np.round(rng.uniform(0.05, 8.0, size=n), 2)
    warranty_years = rng.choice([1, 2, 3], size=n, p=[0.6, 0.3, 0.1])
    in_stock = rng.random(size=n) < 0.85

    catalog = []
    for i in range(n):
        cat = CATEGORIES[cat_idx[i]]
        brand = CATEGORY_TOKENS[cat]["brands"][brand_idx[i]]
        adj = ADJECTIVES[adj_idx[i]]
        noun = CATEGORY_TOKENS[cat]["nouns"][noun_idx[i]]
        model = f"{chr(65 + model_letter_idx[i])}{model_num[i]}"
        name = f"{brand} {adj} {noun} {model}"
        catalog.append({
            "product_id": i + 1,
            "name": name,
            "brand": brand,
            "category": cat,
            "price": float(price[i]),
            "currency": "USD",
            "specs": {
                "color": COLORS[color_idx[i]],
                "material": MATERIALS[material_idx[i]],
                "weight_kg": float(weight_kg[i]),
                "warranty_years": int(warranty_years[i]),
            },
            "in_stock": bool(in_stock[i]),
        })
    return catalog


# --------------------------------------------------------------------------
# build_extraction_set — selector-hostile HTML snippets
# --------------------------------------------------------------------------

def _stock_phrase(in_stock, variant_idx):
    in_variants = ["In stock", "Ships today", "Available now"]
    out_variants = ["Out of stock", "Currently unavailable", "Sold out"]
    pool = in_variants if in_stock else out_variants
    return pool[variant_idx % len(pool)]


def _price_str(price, currency):
    if currency == "USD":
        return f"${price:.2f}"
    if currency == "GBP":
        return f"£{price:.2f}"
    # EUR: comma decimal, symbol suffix
    return f"{price:.2f}".replace(".", ",") + " €"


def _tmpl_nested_divs(product, currency, stock_variant_idx):
    price_str = _price_str(product["price"], currency)
    stock = _stock_phrase(product["in_stock"], stock_variant_idx)
    return (
        f'<div class="prod-card"><h2 class="ttl">{product["name"]}</h2>'
        f'<span class="brand-lbl">{product["brand"]}</span>'
        f'<div class="pricing"><span class="amt">{price_str}</span></div>'
        f'<p class="avail">{stock}</p></div>'
    )


def _tmpl_prose(product, currency, stock_variant_idx):
    price_str = _price_str(product["price"], currency)
    stock = _stock_phrase(product["in_stock"], stock_variant_idx)
    return (
        f"<article><h3>{product['name']}</h3>"
        f"<p>Made by {product['brand']}. Now only {price_str} -- {stock}. "
        f"Grab yours today!</p></article>"
    )


def _tmpl_attributes(product, currency, stock_variant_idx):
    return (
        f'<li class="item" data-name="{product["name"]}" data-brand="{product["brand"]}" '
        f'data-price="{product["price"]:.2f}" data-currency="{currency}" '
        f'data-in-stock="{str(product["in_stock"]).lower()}">'
        f'<span>{product["name"]}</span></li>'
    )


def _tmpl_entity_noise(product, currency, stock_variant_idx):
    price_str = _price_str(product["price"], currency)
    stock = _stock_phrase(product["in_stock"], stock_variant_idx)
    return (
        f'<div class="card">\n\n  <span class="title">{product["name"]}</span>'
        f"&nbsp;&nbsp;<br/>\n  <span class=\"maker\">by&nbsp;{product['brand']}</span>\n"
        f'  <span class="cost">{price_str}</span>\n  <em>{stock}</em>\n</div>'
    )


def _tmpl_broken_tags(product, currency, stock_variant_idx):
    price_str = _price_str(product["price"], currency)
    stock = _stock_phrase(product["in_stock"], stock_variant_idx)
    return (
        f'<ul><li class="p"><b>{product["name"]}<b> — <i>{product["brand"]}</i>'
        f"<p>Price: {price_str}<p>{stock}</ul>"
    )


def _tmpl_cents_implied_stock(product, currency, stock_variant_idx):
    price_cents = int(round(product["price"] * 100))
    cta = "<button>Add to Cart</button>" if product["in_stock"] else '<span class="oos">Currently unavailable</span>'
    return (
        f'<div class="listing" data-price-cents="{price_cents}" data-currency="{currency}">'
        f'<h4>{product["name"]}</h4><span>{product["brand"]}</span>{cta}</div>'
    )


EXTRACTION_TEMPLATES = [
    _tmpl_nested_divs, _tmpl_prose, _tmpl_attributes,
    _tmpl_entity_noise, _tmpl_broken_tags, _tmpl_cents_implied_stock,
]
EXTRACTION_CURRENCIES = ["USD", "EUR", "GBP"]
EXTRACTION_CURRENCY_WEIGHTS = [0.7, 0.2, 0.1]
N_EXTRACTION = 50


def build_extraction_set(seed):
    """PURE builder: list[dict], each {snippet_id, html, gold}. Draws from
    the fixed SCALE=1.0 catalog. gold = {name, brand, price, currency,
    in_stock} for the same product the html was rendered from."""
    catalog = build_catalog(seed, 1.0)
    rng = np.random.default_rng(seed)
    n = N_EXTRACTION

    product_idx = rng.choice(len(catalog), size=n, replace=False)
    template_idx = rng.integers(0, len(EXTRACTION_TEMPLATES), size=n)
    currency_idx = rng.choice(len(EXTRACTION_CURRENCIES), size=n, p=EXTRACTION_CURRENCY_WEIGHTS)
    stock_variant_idx = rng.integers(0, 3, size=n)

    items = []
    for i in range(n):
        product = catalog[product_idx[i]]
        currency = EXTRACTION_CURRENCIES[currency_idx[i]]
        template = EXTRACTION_TEMPLATES[template_idx[i]]
        html = template(product, currency, int(stock_variant_idx[i]))
        items.append({
            "snippet_id": f"ext-{i + 1:03d}",
            "html": html,
            "gold": {
                "name": product["name"],
                "brand": product["brand"],
                "price": product["price"],
                "currency": currency,
                "in_stock": product["in_stock"],
            },
        })
    return items


# --------------------------------------------------------------------------
# build_classification_set — diluted-signal records
# --------------------------------------------------------------------------

N_CLASSIFICATION = 80


def build_classification_set(seed):
    """PURE builder: list[dict], each {record_id, title, description,
    gold_category, gold_brand}. gold_brand is the brand token actually
    embedded in the title (generic or category-specific) -- an extractable
    field, distinct from gold_category which is deliberately diluted (same
    generic-brand-pool + cross-category-noun-noise mechanism as module 14's
    title construction) so it takes real classification, not a keyword
    lookup."""
    catalog = build_catalog(seed, 1.0)
    rng = np.random.default_rng(seed)
    n = N_CLASSIFICATION
    n_cat = len(CATEGORIES)

    product_idx = rng.choice(len(catalog), size=n, replace=False)
    generic_roll = rng.random(size=n) < GENERIC_BRAND_FRAC
    cross_roll = rng.random(size=n) < CROSS_NOUN_NOISE_FRAC
    cross_offset = rng.integers(1, n_cat, size=n)
    brand_idx = rng.integers(0, 4, size=n)
    noun_idx = rng.integers(0, 6, size=n)
    adj_idx = rng.integers(0, len(ADJECTIVES), size=n)
    model_num = rng.integers(100, 999, size=n)
    model_letter_idx = rng.integers(0, 26, size=n)
    desc_template_idx = rng.integers(0, len(DESC_TEMPLATES), size=n)
    desc_cross_roll = rng.random(size=n) < 0.3
    desc_cross_offset = rng.integers(1, n_cat, size=n)

    items = []
    for i in range(n):
        product = catalog[product_idx[i]]
        cat = product["category"]
        cat_i = CATEGORIES.index(cat)

        brand = GENERIC_BRANDS[brand_idx[i]] if generic_roll[i] else CATEGORY_TOKENS[cat]["brands"][brand_idx[i]]
        noun_cat_i = (cat_i + cross_offset[i]) % n_cat if cross_roll[i] else cat_i
        noun = CATEGORY_TOKENS[CATEGORIES[noun_cat_i]]["nouns"][noun_idx[i]]
        adj = ADJECTIVES[adj_idx[i]]
        model = f"{chr(65 + model_letter_idx[i])}{model_num[i]}"
        title = f"{brand} {adj} {noun} {model}"

        description = DESC_TEMPLATES[desc_template_idx[i]].format(adj=adj.lower())
        if desc_cross_roll[i]:
            other_cat = CATEGORIES[(cat_i + desc_cross_offset[i]) % n_cat]
            description += f" Popular among {CATEGORY_ACTIVITY[other_cat]} fans this season."

        items.append({
            "record_id": f"cls-{i + 1:03d}",
            "title": title,
            "description": description,
            "gold_category": cat,
            "gold_brand": brand,
        })
    return items


# --------------------------------------------------------------------------
# build_dedup_set — title variants of the same product
# --------------------------------------------------------------------------

N_DEDUP_CLUSTERS = 20
DEDUP_VARIANT_COUNTS = [1, 2, 3, 4]
DEDUP_VARIANT_WEIGHTS = [0.15, 0.35, 0.35, 0.15]


def _distort_abbreviation(name):
    tokens = name.split()
    tokens[1] = ABBR_MAP.get(tokens[1], tokens[1][:4] + ".")
    return " ".join(tokens)


def _distort_reorder(name):
    brand, adj, noun, model = name.split()
    return f"{adj} {noun} {model} {brand}"


def _distort_punctuation(name):
    brand, adj, noun, model = name.split()
    return f"{brand}, {adj} {noun} - {model}"


def _distort_brand_swap(name):
    brand, adj, noun, model = name.split()
    return f"{adj} {noun} {model} ({brand})"


DEDUP_DISTORTIONS = [_distort_abbreviation, _distort_reorder, _distort_punctuation, _distort_brand_swap]


def build_dedup_set(seed):
    """PURE builder: list[dict], each {item_id, title, gold_cluster_id}.
    ~20 clusters (one canonical product each), 1-4 title variants per
    cluster (variant 0 always the untouched catalog name; later variants
    each apply one of 4 distortions: abbreviation, token reorder,
    punctuation/spacing change, brand-position swap). Final list order is
    shuffled so items aren't trivially grouped by cluster."""
    catalog = build_catalog(seed, 1.0)
    rng = np.random.default_rng(seed)

    cluster_product_idx = rng.choice(len(catalog), size=N_DEDUP_CLUSTERS, replace=False)
    variant_counts = rng.choice(DEDUP_VARIANT_COUNTS, size=N_DEDUP_CLUSTERS, p=DEDUP_VARIANT_WEIGHTS)

    items = []
    counter = 0
    for c in range(N_DEDUP_CLUSTERS):
        product = catalog[cluster_product_idx[c]]
        count = int(variant_counts[c])
        for v in range(count):
            counter += 1
            if v == 0:
                title = product["name"]
            else:
                distortion_idx = int(rng.integers(0, len(DEDUP_DISTORTIONS)))
                title = DEDUP_DISTORTIONS[distortion_idx](product["name"])
            items.append({
                "item_id": f"ddp-{counter:03d}",
                "title": title,
                "gold_cluster_id": c,
            })

    perm = rng.permutation(len(items))
    return [items[i] for i in perm]


# --------------------------------------------------------------------------
# build_rag_corpus — synthetic "Sandbox Handbook" (fixed strings, no rng)
# --------------------------------------------------------------------------

_HANDBOOK_DOCS = [
    {
        "doc_id": "ports-policy",
        "title": "Port Allocation Policy",
        "text": (
            "# Port Allocation Policy\n\n"
            "Every module that ships a docker-compose stack gets its own block of "
            "host ports, recorded in a central conventions table so two modules can "
            "run at the same time without a collision. Postgres-backed modules use "
            "the `543NN` range, where `NN` is the module number; modules with other "
            "services pick a module-specific range instead.\n\n"
            "The llm-in-pipelines module's Ollama service listens on host port "
            "11439 by default, overridable via the SANDBOX_15_OLLAMA_PORT "
            "environment variable. Not every module needs a port at all: the "
            "stats-and-ml-foundations module runs entirely in pure Python and "
            "needs no docker-compose file at all, since it has no service to "
            "expose.\n"
        ),
    },
    {
        "doc_id": "hint-ladder",
        "title": "The Three-Hint Ladder",
        "text": (
            "# The Three-Hint Ladder\n\n"
            "Every task ships exactly three hint files. hint-1.md only points in a "
            "direction and contains no specifics -- it names a concept or asks a "
            "question, nothing more. hint-2.md narrows the answer down to a "
            "specific mechanism or approach. hint-3.md is the last resort: concrete "
            "guidance close to pseudocode.\n\n"
            "No hint file, and no file anywhere in the sandbox, ever contains a "
            "ready-made reference solution. The ladder is designed so a learner "
            "who is stuck can ask for progressively more help without ever being "
            "handed the answer outright.\n"
        ),
    },
    {
        "doc_id": "verification-contract",
        "title": "The Verification Contract",
        "text": (
            "# The Verification Contract\n\n"
            "A validator that cannot confirm a task is solved must print a line "
            "beginning with the literal text NOT PASSED: followed by a short, "
            "human-readable reason, then exit with status code 1. A validator that "
            "confirms success prints PASSED and exits with status code 0.\n\n"
            "Tracebacks must never reach the learner's terminal. Any unexpected "
            "exception raised while grading a task is caught and reported as a "
            "NOT PASSED line instead, so a half-finished scaffold fails cleanly "
            "rather than dumping a Python stack trace.\n"
        ),
    },
    {
        "doc_id": "data-generation-rules",
        "title": "Data Generation Rules",
        "text": (
            "# Data Generation Rules\n\n"
            "Every generator script in the sandbox honors a SCALE environment "
            "variable, defaulting to 1.0, that scales the size of the generated "
            "dataset up or down. Generation is deterministic: a fixed random seed "
            "means two runs at the same SCALE produce byte-identical output.\n\n"
            "Generated data lives inside a data/ directory and is excluded from "
            "version control, with a single exception: the file "
            "data/ground-truth.json, which is committed so every learner starts "
            "from the same answer key regardless of whether they have regenerated "
            "their own local copy of the larger data files.\n"
        ),
    },
    {
        "doc_id": "python-tooling",
        "title": "Python Tooling Conventions",
        "text": (
            "# Python Tooling Conventions\n\n"
            "Each module owns its own pyproject.toml and a committed uv.lock "
            "file, so its dependency set is pinned independently of every other "
            "module. All commands run through uv run rather than a bare python "
            "invocation, which guarantees the interpreter and installed packages "
            "match what the lockfile records.\n\n"
            "Where a module touches Postgres, database access goes through the "
            "psycopg driver at major version 3, never psycopg2 and never an ORM, "
            "unless a task is specifically about evaluating an ORM's behavior.\n"
        ),
    },
    {
        "doc_id": "capstone-checkpoints",
        "title": "Capstone Checkpoint Structure",
        "text": (
            "# Capstone Checkpoint Structure\n\n"
            "Every module that ends in a capstone task breaks it into three "
            "checkpoints. CP1 is the steady-state pass: the pipeline runs against "
            "clean, well-behaved input and must hit its quality thresholds. CP2 is "
            "the chaos pass: the same pipeline faces messier input, injected "
            "faults, or degraded upstream services, and must degrade gracefully "
            "instead of crashing outright.\n\n"
            "CP3 is the design memo: the learner writes a DESIGN.md explaining the "
            "system's architecture and tradeoffs, and then CP1 and CP2 are "
            "re-run as subprocesses to prove the write-up describes a system that "
            "still actually works.\n"
        ),
    },
]

_HANDBOOK_QA = [
    {
        "question": "What host port does the llm-in-pipelines module's Ollama service listen on by default?",
        "gold_doc_id": "ports-policy",
        "gold_answer_substring": "11439",
        "gold_keywords": ["11439", "ollama", "port"],
    },
    {
        "question": "Which environment variable overrides module 15's Ollama port?",
        "gold_doc_id": "ports-policy",
        "gold_answer_substring": "SANDBOX_15_OLLAMA_PORT",
        "gold_keywords": ["SANDBOX_15_OLLAMA_PORT"],
    },
    {
        "question": "Does the stats-and-ml-foundations module use docker-compose?",
        "gold_doc_id": "ports-policy",
        "gold_answer_substring": "needs no docker-compose file at all",
        "gold_keywords": ["stats-and-ml-foundations", "docker-compose", "pure Python"],
    },
    {
        "question": "How many hint files does every task ship?",
        "gold_doc_id": "hint-ladder",
        "gold_answer_substring": "exactly three hint files",
        "gold_keywords": ["three", "hint"],
    },
    {
        "question": "What does hint-1.md contain?",
        "gold_doc_id": "hint-ladder",
        "gold_answer_substring": "only points in a direction and contains no specifics",
        "gold_keywords": ["hint-1", "direction", "no specifics"],
    },
    {
        "question": "What literal text must a failing validator print at the start of its output line?",
        "gold_doc_id": "verification-contract",
        "gold_answer_substring": "NOT PASSED:",
        "gold_keywords": ["NOT PASSED"],
    },
    {
        "question": "What exit status code does a passing validator use?",
        "gold_doc_id": "verification-contract",
        "gold_answer_substring": "exits with status code 0",
        "gold_keywords": ["exit", "status code 0", "PASSED"],
    },
    {
        "question": "What must never reach the learner's terminal?",
        "gold_doc_id": "verification-contract",
        "gold_answer_substring": "Tracebacks must never reach the learner's terminal",
        "gold_keywords": ["traceback"],
    },
    {
        "question": "What is the default value of the SCALE environment variable?",
        "gold_doc_id": "data-generation-rules",
        "gold_answer_substring": "defaulting to 1.0",
        "gold_keywords": ["SCALE", "1.0"],
    },
    {
        "question": "Which single generated file is committed to version control?",
        "gold_doc_id": "data-generation-rules",
        "gold_answer_substring": "data/ground-truth.json",
        "gold_keywords": ["ground-truth.json", "committed"],
    },
    {
        "question": "What file does each module commit alongside its pyproject.toml?",
        "gold_doc_id": "python-tooling",
        "gold_answer_substring": "uv.lock",
        "gold_keywords": ["uv.lock"],
    },
    {
        "question": "Which major version of psycopg does the sandbox require?",
        "gold_doc_id": "python-tooling",
        "gold_answer_substring": "psycopg driver at major version 3",
        "gold_keywords": ["psycopg", "3"],
    },
    {
        "question": "How many checkpoints does a capstone task break into?",
        "gold_doc_id": "capstone-checkpoints",
        "gold_answer_substring": "three checkpoints",
        "gold_keywords": ["three", "checkpoints"],
    },
    {
        "question": "What happens during CP2 of a capstone?",
        "gold_doc_id": "capstone-checkpoints",
        "gold_answer_substring": "CP2 is the chaos pass",
        "gold_keywords": ["CP2", "chaos"],
    },
    {
        "question": "What does CP3 require the learner to write?",
        "gold_doc_id": "capstone-checkpoints",
        "gold_answer_substring": "CP3 is the design memo",
        "gold_keywords": ["CP3", "design memo", "DESIGN.md"],
    },
]


def build_rag_corpus(seed):
    """PURE builder (no rng draw -- the handbook is fixed, synthetic content,
    deliberately NOT copied from the live repo so it stays deterministic and
    drift-proof as the repo evolves). Returns (docs, qa):
      docs: list[dict] {doc_id, title, path, text}
      qa:   list[dict] {question, gold_doc_id, gold_answer_substring, gold_keywords}
    Every gold_answer_substring is verified (see generate()) to appear
    verbatim in its gold_doc_id's text."""
    del seed  # content is fixed; seed kept for signature symmetry with the other builders
    docs = [
        {"doc_id": d["doc_id"], "title": d["title"], "path": f"corpus/{d['doc_id']}.md", "text": d["text"]}
        for d in _HANDBOOK_DOCS
    ]
    qa = list(_HANDBOOK_QA)
    return docs, qa


# --------------------------------------------------------------------------
# Ground truth
# --------------------------------------------------------------------------

def _canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _data_sha(catalog, extraction, classification, dedup, docs, qa):
    payload = {
        "catalog": catalog,
        "extraction": extraction,
        "classification": classification,
        "dedup": dedup,
        "corpus_docs": docs,
        "corpus_qa": qa,
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _ground_truth(catalog, extraction, classification, dedup, docs, qa, seed, scale):
    n_clusters = len({item["gold_cluster_id"] for item in dedup})
    return {
        "seed": seed,
        "scale": scale,
        "categories": CATEGORIES,
        "n_catalog": len(catalog),
        "n_extraction": len(extraction),
        "n_classification": len(classification),
        "n_dedup": len(dedup),
        "n_clusters": n_clusters,
        "n_corpus_docs": len(docs),
        "n_qa": len(qa),
        "data_sha": _data_sha(catalog, extraction, classification, dedup, docs, qa),
    }


def _strip(items, drop_keys):
    return [{k: v for k, v in item.items() if k not in drop_keys} for item in items]


def _verify_rag_gold(docs, qa):
    text_by_id = {d["doc_id"]: d["text"] for d in docs}
    for q in qa:
        doc_text = text_by_id.get(q["gold_doc_id"])
        if doc_text is None:
            raise ValueError(f"QA references unknown doc_id: {q['gold_doc_id']!r}")
        if q["gold_answer_substring"] not in doc_text:
            raise ValueError(
                f"gold_answer_substring {q['gold_answer_substring']!r} not found in doc "
                f"{q['gold_doc_id']!r} for question {q['question']!r}"
            )


def generate():
    scale = float(os.environ.get("SCALE", "1.0"))
    print(f"SCALE={scale} SEED={SEED}")

    catalog = build_catalog(SEED, scale)
    extraction = build_extraction_set(SEED)
    classification = build_classification_set(SEED)
    dedup = build_dedup_set(SEED)
    docs, qa = build_rag_corpus(SEED)
    _verify_rag_gold(docs, qa)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    (DATA_DIR / "extraction.json").write_text(
        json.dumps(_strip(extraction, {"gold"}), indent=2), encoding="utf-8"
    )
    (DATA_DIR / "classification.json").write_text(
        json.dumps(_strip(classification, {"gold_category", "gold_brand"}), indent=2), encoding="utf-8"
    )
    (DATA_DIR / "dedup.json").write_text(
        json.dumps(_strip(dedup, {"gold_cluster_id"}), indent=2), encoding="utf-8"
    )
    for doc in docs:
        (CORPUS_DIR / f"{doc['doc_id']}.md").write_text(doc["text"], encoding="utf-8")

    gt = _ground_truth(catalog, extraction, classification, dedup, docs, qa, SEED, scale)
    GROUND_TRUTH_PATH.write_text(json.dumps(gt, indent=2), encoding="utf-8")

    print(f"wrote data/extraction.json ({len(extraction)} snippets)")
    print(f"wrote data/classification.json ({len(classification)} records)")
    print(f"wrote data/dedup.json ({len(dedup)} items, {gt['n_clusters']} clusters)")
    print(f"wrote data/corpus/*.md ({len(docs)} docs, {len(qa)} qa pairs verified)")
    print(f"ground truth written: {GROUND_TRUTH_PATH}")
    print(f"  n_catalog={gt['n_catalog']} n_extraction={gt['n_extraction']} n_classification={gt['n_classification']}")
    print(f"  n_dedup={gt['n_dedup']} n_clusters={gt['n_clusters']} n_corpus_docs={gt['n_corpus_docs']} n_qa={gt['n_qa']}")
    print(f"  data_sha={gt['data_sha']}")


if __name__ == "__main__":
    sys.exit(generate())
