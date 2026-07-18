# Module 14 design — SPOILERS, learner off-limits

Do not read this before attempting the module's tasks. It documents the
shared harness API every task and validator depends on, the dataset schema
and RNG draw order, the defect-planting and confound construction, the
committed ground-truth values, and the verification philosophy per task
type.

This file is the shared contract for every agent working on this module
(infra, generator, task authors, validators). If you change something here,
regenerate and reverify and update every consumer in the same change.

## No docker stack

Module 14 is pure Python (numpy, pandas, polars, pyarrow, scipy, scikit-learn,
matplotlib, torch, pytest). There is no `docker-compose.yml` and no ports
table entry in `CONVENTIONS.md`. `requires-python = ">=3.12,<3.13"` is a hard
pin, not a floor — verified this session that torch 2.13.0+cpu has no
wheel for 3.14 (the ambient interpreter on this machine) but resolves,
installs, and imports cleanly on 3.12.12 via `uv python`. Do not relax the
upper bound without re-verifying torch availability for the new ceiling.

## Harness API (`harness/common.py`)

Every third-party import is lazy inside the function that needs it;
importing `harness.common` has zero side effects (verified: no numpy/pandas/
matplotlib import at module load time).

```python
MODULE_ROOT: Path                    # 14-stats-and-ml-foundations/
DATA_DIR: Path                       # MODULE_ROOT / "data"
GROUND_TRUTH_PATH: Path              # DATA_DIR / "ground-truth.json"
OBSERVATIONS_PATH: Path              # DATA_DIR / "observations.parquet"

def not_passed(reason) -> NoReturn   # print "NOT PASSED: <reason>", sys.exit(1)
def passed(msg="") -> NoReturn       # print "PASSED[: msg]", sys.exit(0)
def guarded(fn) -> Callable          # decorator: unexpected exceptions (incl. NotImplementedError) -> NOT PASSED; SystemExit re-raised
def _last_line(text) -> str          # last non-empty line of a stream/error text

def time_it(fn, *a, **k) -> tuple    # (result, elapsed_seconds) via time.perf_counter
def write_baseline(path, obj) -> Path  # write gitignored *-local.json under MODULE_ROOT (relative paths resolved against it)
def read_baseline(path) -> dict|None   # read it back, or None if absent

def load_ground_truth() -> dict      # reads GROUND_TRUTH_PATH or NOT PASSED("...run generate.py first")
def load_observations() -> pd.DataFrame  # reads OBSERVATIONS_PATH via pyarrow or NOT PASSED("...run generate.py first")

def approx(a, b, rel=1e-6, abs_=1e-9) -> bool           # float/money tolerance compare
def check_close(name, got, want, rel=1e-6, abs_=1e-9) -> (bool, str)  # same, with a diagnostic message

def require_figure(fig, min_axes=1) -> (bool, str)  # structural check: is a Figure, has >= min_axes Axes, at least one axis has drawn artists (lines/patches/collections/images)
```

Design notes for task authors:

- **`load_observations`** always returns the FULL dataset at whatever
  `SCALE` it was generated at — there is no per-task filtering. Tasks that
  need a train/test split must fix their own split seed (see "ML tasks"
  below) so the learner and the validator agree on which rows are held out.
- **`require_figure`** is a floor, not a rubric. It confirms a figure with
  actual drawn content exists — it cannot judge axis labels, chart choice,
  or whether the plot answers the task's question. Combine it with a
  numeric check on the underlying data wherever the task has a "the plot
  should show X" claim that reduces to a number (e.g. "the CI should not
  contain 0" is checkable directly on the interval, independent of the
  plot).
- **`check_close` / `approx`**: default `rel=1e-6` is appropriate for
  values computed by float arithmetic through the same code path as the
  reference (e.g. re-deriving a sum). Loosen `rel` explicitly (document why
  in the validator) for anything that legitimately has sampling variance —
  e.g. a bootstrap CI's bounds, an A/B test's p-value — rather than
  tightening the tolerance until it's flaky.
- **`guarded`** has identical semantics to modules 10/11 — it wraps a
  validator's sync entry point; unexpected exceptions and
  `NotImplementedError` both become `NOT PASSED`, `SystemExit` passes
  through untouched.

## Dataset schema (`data/observations.parquet`)

One row per scrape observation. 12 columns:

| column | dtype | meaning |
|---|---|---|
| `obs_id` | int64 | 1-based, unique per row |
| `product_id` | int64 | 1-based; many observations share a `product_id` over time |
| `category` | str | one of `CATEGORIES` (below) |
| `title` | str | `"<brand> <adjective> <noun> <model>"`, category signal diluted (see Title construction) |
| `price` | float64 | log-normal draw per category; ~4.5% of rows carry a planted defect (see Defects) |
| `currency` | str | mostly `"USD"`; ~2% left as `"EUR"`/`"GBP"` (un-normalized currency) |
| `scraped_at` | datetime64[us] | within a fixed 90-day window, weekday- and daytime-biased |
| `in_stock` | bool | `P(True) = 0.85`, iid |
| `seller_rating` | float64 | `clip(N(4.2, 0.5), 1.0, 5.0)`, rounded to 1 decimal |
| `source_site` | str | one of `["alpha-shop", "beta-mart", "gamma-store"]`, weights `[0.5, 0.3, 0.2]` |
| `discount_pct` | float64 | 0–0.6, category-confounded with `units_sold` (see Confound) |
| `units_sold` | int64 | Poisson draw, category-confounded with `discount_pct` (see Confound) |

`CATEGORIES = ["electronics", "home-goods", "kitchen", "toys", "sporting-goods", "apparel", "books", "garden"]`
(fixed rank order for the category Zipf draw, most to least popular).

## Generation (`generate.py`)

`build_observations(seed, n) -> (df, labels)` is PURE (numpy + pandas only,
no file I/O). `SEED = 141414`. `n_obs = round(60000 * SCALE)`,
`n_products = max(1, round(n_obs / 7.5))` (≈ 8000 at `SCALE=1.0`).

### Draw order (fixed — do not reorder without regenerating and updating every consumer)

A single `rng = np.random.default_rng(seed)` is consumed in this exact
order:

- **G1** `product_category_idx = rng.choice(8, size=n_products, p=category_weights())`
  — assigns each of the `n_products` products a category. `category_weights()`
  is Zipf `1/rank^1.1` over `CATEGORIES` in rank order (no rng draw).
- **G2** `product_weights = zipf_weights(n_products, s=0.4)` — per-product
  popularity, deterministic, **no rng draw**. `s=0.4` is deliberately flatter
  than the category exponent (1.1): at `s=1.1` over an 8000-product pool,
  60000 draws would only ever touch ~5400 distinct products (the Zipf tail
  starves most of the pool); `s=0.4` keeps "popular products get scraped
  more" while still touching ~7950–8000 of the ~8000 products at
  `SCALE=1.0` (verified: 7968).
- **G3** `obs_product_idx = rng.choice(n_products, size=n, p=product_weights)`
  — which product each observation belongs to. `category_idx =
  product_category_idx[obs_product_idx]` (a lookup, not a draw — every
  observation of a given product shares that product's category).
- **G4** clean price: `z = rng.normal(size=n)`; `clean_price =
  round(exp(ln(median_cat) + sigma_cat * z), 2)`, clipped `>= 0.5`. Per-
  category `(median, sigma)` — see `CATEGORY_PRICE_PROFILE` table below.
  `clean_price` is the pre-defect value, kept in `labels` for validators.
- **G5** title tokens, in this sub-order: `brand_idx = rng.integers(0, 4,
  size=n)`, `adj_idx = rng.integers(0, 10, size=n)`, `noun_idx =
  rng.integers(0, 6, size=n)`, `model_num = rng.integers(100, 999, size=n)`,
  `model_letter_idx = rng.integers(0, 26, size=n)`, `cross_noise_roll =
  rng.random(size=n) < 0.25`, `cross_cat_offset = rng.integers(1, 8,
  size=n)` (→ `cross_cat_idx = (category_idx + cross_cat_offset) % 8`,
  guarantees a *different* category), `generic_brand_roll = rng.random(size=n)
  < 0.30`. See Title construction below.
- **G6** currency: `non_usd_roll = rng.random(size=n) < 0.02`,
  `non_usd_code_idx = rng.integers(0, 2, size=n)` (indexes
  `["EUR", "GBP"]`).
- **G7** `scraped_at`: weekday-biased day pick + daytime-clustered hour.
  `day_weight` over the 90-day window is `1.3` on weekday offsets, `0.7` on
  weekend offsets (normalized), `day_offset = rng.choice(90, size=n,
  p=day_weight)`; `hour_frac = clip(N(13.0, 4.0), 0, 23.99)` (single
  daytime peak ≈ 1pm ± 4h). Window: `[SCRAPE_WINDOW_END - 90d,
  SCRAPE_WINDOW_END)`, `SCRAPE_WINDOW_END = 2026-01-01` (fixed constant, not
  "today" — keeps generation reproducible independent of when it's run).
- **G8** `in_stock = rng.random(size=n) < 0.85`.
- **G9** `seller_rating = round(clip(N(4.2, 0.5), 1.0, 5.0), 1)`.
- **G10** `source_site`: `rng.choice(3, size=n, p=[0.5, 0.3, 0.2])` over
  `["alpha-shop", "beta-mart", "gamma-store"]`.
- **G11** `discount_pct` / `units_sold` confound — see Confound below.
- **G12** price defects — `defect_idx = rng.choice(n, size=round(0.045*n),
  replace=False)`, split via `np.array_split` into 4 equal-ish contiguous
  chunks (order as drawn by `rng.choice`, not re-shuffled) assigned to
  `["negative", "zero", "missing_decimal", "nan"]` in that order. See
  Defects below.

### Per-category price profile (`CATEGORY_PRICE_PROFILE`, median/sigma)

| category | median | sigma |
|---|---|---|
| electronics | 150.0 | 0.90 |
| home-goods | 45.0 | 0.65 |
| kitchen | 34.0 | 0.55 |
| toys | 22.0 | 0.50 |
| sporting-goods | 58.0 | 0.70 |
| apparel | 28.0 | 0.50 |
| books | 14.0 | 0.35 |
| garden | 38.0 | 0.60 |

### Title construction

Each category has 4 brand tokens and 6 noun tokens (`CATEGORY_TOKENS`); a
shared `ADJECTIVES` pool of 10 is category-agnostic by design (carries no
category signal). Title = `"{brand} {adj} {noun} {model}"`,
`model = f"{chr(65+model_letter_idx)}{model_num}"` (e.g. `"K482"`).

Two deliberate signal-dilution mechanisms, both needed to keep a title-only
classifier learnable-but-imperfect rather than trivially perfect:

- **Generic brand pool** (`GENERIC_BRANDS`, 4 tokens shared across ALL
  categories): `generic_brand_roll` (30% of rows) replaces the
  category-specific brand with a generic one, indexed by the same
  `brand_idx`. Without this, brand alone perfectly predicts category (the
  category-exclusive brand lists are otherwise disjoint) and a TF-IDF +
  logistic-regression classifier hits macro-F1 = 1.0 — too easy, no
  headroom for feature engineering (task 11) to matter.
- **Cross-category noun noise** (`cross_noise_roll`, 25% of rows): swaps the
  noun for one drawn from a *different* category's noun list
  (`cross_cat_idx`, guaranteed `!= category_idx`), while `category` (the
  label) and `brand` are untouched.

Verified empirically this session (TF-IDF + `LogisticRegression`,
80/20 stratified split, `random_state=0`, full `SCALE=1.0` data):
**macro-F1 ≈ 0.90**, per-class F1 ranging 0.86–0.95 — comfortably above the
"~0.8+" target, not trivially perfect. `electronics`/`home-goods` (both
brand-token-rich, largest classes) score highest; `apparel`/`books`/`garden`
(smaller classes, more noun-noise proportionally) score lowest. This gap is
intentional headroom for task 11 (feature engineering) and task 13
(capstone).

### Defects (`price` column, ~4.5% of rows total)

`DEFECT_FRAC = 0.045`. Four kinds, roughly equal counts (exactly equal
except for the `n % 4` remainder from `np.array_split`, which
`np.array_split` assigns to the first chunks):

| kind | transformation |
|---|---|
| `negative` | `price = -clean_price` |
| `zero` | `price = 0.0` |
| `missing_decimal` | `price = round(clean_price * 100, 2)` (simulates a dropped decimal point, e.g. `$19.99` scraped as `$1999`) |
| `nan` | `price = NaN` (an "N/A" string that parsed to missing) |

`labels["defect_mask"]` (bool, row-aligned) and `labels["defect_kind"]`
(str, `""` for non-defective rows) give validators the exact partition
without re-deriving it. `labels["clean_price"]` is the pre-defect value for
every row (defective or not), so a validator can verify e.g. that the
`missing_decimal` kind really is `price / 100 == clean_price`.

Currency (`non_usd_mask`) is a **separate, independent** data-quality axis
from price defects — a row can be both, either, or neither. 2% of rows
(`NON_USD_FRAC`) get a non-USD currency code; this is not counted in
`n_parsing_errors` / `parsing_error_kind_counts` (those cover `price` only).

### Genuine outliers

`labels["genuine_outlier_mask"]`: per category, `threshold = percentile(
clean_price[category], 99.5)` computed over the CLEAN (pre-defect) draw for
that category's full population (not just valid rows). A row is a genuine
outlier iff `clean_price > threshold` AND the row is otherwise valid
(`~defect_mask & ~non_usd_mask`) — i.e., a real, usable, unusually high
price, not a parsing artifact. This is the reference task 05 (outliers vs.
parsing errors) grades against: the whole point of that task is that a
naive "flag anything above 3 std devs" rule catches both genuine outliers
AND some of the `missing_decimal`/`negative` defects, and the task is to
separate them properly.

### Confound (`discount_pct` / `units_sold`, task 09)

Both driven by category, via two fixed lookup tables:

```python
CATEGORY_BASE_DISCOUNT = {
    "electronics": 0.08, "home-goods": 0.15, "kitchen": 0.18, "toys": 0.30,
    "sporting-goods": 0.10, "apparel": 0.35, "books": 0.25, "garden": 0.20,
}
CATEGORY_BASE_UNITS = {
    "electronics": 15.0, "home-goods": 25.0, "kitchen": 30.0, "toys": 60.0,
    "sporting-goods": 20.0, "apparel": 55.0, "books": 45.0, "garden": 28.0,
}
DISCOUNT_NOISE_SIGMA = 0.05
WITHIN_CATEGORY_EFFECT = 0.10
```

```python
discount_pct = clip(CATEGORY_BASE_DISCOUNT[cat] + N(0, 0.05), 0, 0.6)   # round 3
lambda_units = max(CATEGORY_BASE_UNITS[cat] * (1 + 0.10 * (discount_pct - CATEGORY_BASE_DISCOUNT[cat])), 0.5)
units_sold = Poisson(lambda_units)
```

`CATEGORY_BASE_DISCOUNT` and `CATEGORY_BASE_UNITS` are constructed to be
positively associated ACROSS categories (cheap/impulse categories — toys,
apparel, books — both discount more and sell more units baseline), while
the WITHIN-category effect of `discount_pct` on `units_sold` is deliberately
weak (`WITHIN_CATEGORY_EFFECT = 0.10`, applied only to the small
`discount_noise` deviation from the category's own baseline, not to the
baseline itself).

Verified empirically this session (full `SCALE=1.0` data): **pooled
Pearson correlation(`discount_pct`, `units_sold`) ≈ 0.794**; **within-
category correlation ranges ≈ 0.006 (electronics) to ≈ 0.063 (toys)** — a
textbook Simpson's-paradox confound. A validator for task 09 recomputes
both the pooled statistic (on `load_observations()`) and, independently,
the reference category tables above (importable from `generate.py:
CATEGORY_BASE_DISCOUNT, CATEGORY_BASE_UNITS, WITHIN_CATEGORY_EFFECT`, or via
`labels["confound"]` from `build_observations`) to grade whether the
learner's analysis correctly identifies category as the confounder rather
than concluding "discounting drives sales."

### `labels` dict (hidden ground truth, from `build_observations` only — never written to the parquet)

```python
{
    "clean_price": np.ndarray[float64],       # pre-defect price, row-aligned
    "defect_mask": np.ndarray[bool],          # row-aligned
    "defect_kind": np.ndarray[object/str],    # "" or one of the 4 kinds, row-aligned
    "non_usd_mask": np.ndarray[bool],         # row-aligned
    "genuine_outlier_mask": np.ndarray[bool], # row-aligned
    "valid_mask": np.ndarray[bool],           # ~defect_mask & ~non_usd_mask, row-aligned
    "product_category": np.ndarray[str],      # indexed by product_id - 1 (length n_products)
    "category_price_profile": dict,           # == CATEGORY_PRICE_PROFILE
    "confound": {
        "category_base_discount": dict, "category_base_units": dict,
        "discount_noise_sigma": float, "within_category_effect": float,
    },
}
```

Validators call `build_observations(SEED, n)` directly (importing
`generate.py`) to reconstruct these in-memory — never from a hidden file.
`n` must match what `data/ground-truth.json["n_obs"]` reports for the
validator's expected scale, or the reconstruction won't line up with the
committed parquet.

## Committed ground truth (`data/ground-truth.json`)

Computed by `_ground_truth(df, labels, seed, scale)` — iterates the built
DataFrame, never hand-computed. Verified `SCALE=1.0` values (this session,
reproduced byte-identical across two independent full runs):

```json
{
  "seed": 141414,
  "scale": 1.0,
  "n_obs": 60000,
  "n_products": 7968,
  "categories": ["electronics","home-goods","kitchen","toys","sporting-goods","apparel","books","garden"],
  "per_category_count": {"electronics": 23673, "home-goods": 11171, "kitchen": 7109, "toys": 5470, "sporting-goods": 4186, "apparel": 3012, "books": 2665, "garden": 2714},
  "per_category_count_valid": {"electronics": 22184, "home-goods": 10487, "kitchen": 6629, "toys": 5133, "sporting-goods": 3954, "apparel": 2807, "books": 2480, "garden": 2546},
  "n_parsing_errors": 2700,
  "parsing_error_kind_counts": {"negative": 675, "zero": 675, "missing_decimal": 675, "nan": 675},
  "n_non_usd": 1138,
  "n_nan_price": 675,
  "valid_price_sum": 6459299.47,
  "valid_price_mean": 114.89,
  "valid_price_median": 53.79,
  "valid_price_p99": 874.19,
  "n_genuine_outliers": 285,
  "data_sha": "e2c7e74ebd5acadaa798eec02c7c4c7de847cf9c0bc1e820594ad41d9d8dc5a3"
}
```

`data_sha` = sha256 of `df.to_csv(index=False, lineterminator="\n")` —
canonical serialization of the full built DataFrame, used to detect any
drift in the generator (draw order, formula, or dependency version change).
Reproduced identically across two independent `uv run python generate.py`
runs this session; `GROUND_TRUTH_ONLY=1` also reproduces it (parquet write
is skipped, ground truth is not affected by that skip). Any future change
to `generate.py` that alters `data_sha` at `SCALE=1.0` must be treated as a
breaking change to every task's answer key.

`valid_price_*` and any money figure must be compared with a small float
tolerance in validators (`approx` / `check_close`), never exact-decimal
equality.

## Verification philosophy per task type

- **Arc A / Arc B (numpy, EDA, matplotlib, stats)**: validators check
  numeric answers against `load_ground_truth()` or a validator-recomputed
  reference (via `build_observations` in-memory, mirroring modules 10/11's
  pure-builder pattern) within a float tolerance, plus `require_figure` for
  any task whose deliverable includes a plot. Visual correctness (labels,
  chosen chart type, whether it actually communicates the finding) is
  human-checked — the validator can only prove a plot exists and has drawn
  content, never that it's a *good* plot.
- **Arc C (sklearn, PyTorch)**: metric thresholds (accuracy / F1 / etc.) on
  a held-out split, with a **fixed split seed** baked into both the task
  scaffold and its validator so the learner's train/test split and the
  validator's grading split are the same rows. Do not let a task compute
  its own random split without pinning the seed — otherwise the validator
  can't reproduce what the learner saw.
- **Timing tasks** (task 01's vectorization-vs-loop speedup, and any Arc C
  timing comparison): relative to a machine-local baseline only, via
  `write_baseline` / `read_baseline` (gitignored `*-local.json`) — never an
  absolute wall-clock number, same discipline as module 11.

## Per-task namespacing

Unlike modules 10/12 (shared external services needing a `tNN:` key
convention), module 14 has **no shared external state** — no database, no
server. Every task reads the same read-only `data/observations.parquet`;
nothing here mutates it. Each task confines its own scratch files
(baselines, intermediate artifacts) to a gitignored `scratch/` or
`scratch-*/` directory under its own task folder.
