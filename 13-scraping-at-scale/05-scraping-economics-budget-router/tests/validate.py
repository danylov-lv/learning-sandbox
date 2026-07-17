"""Validator for 13-scraping-at-scale task 05 -- scraping-economics-budget-router.

Independent of the learner's code in every way that matters: it never
trusts anything `scrape_with_budget` claims about its own cost, and the
completeness/price/title/currency oracle comes straight from
`load_catalog()`/`load_ground_truth()` (the target's own generation-time
data, computed by `generate.py`, untouched by the learner's scraper).

Checks, in order:

  1. `src.costmodel.estimate_cost`/`project_per_million` sanity -- a few
     known (n_products, n_rendered) -> cost pairs reproduced from ground
     truth's `cost_model` (all-http / all-render / mixed), cheap and fails
     fast before any network traffic if the arithmetic is wrong.
  2. Reset a fresh client, call `scrape_with_budget(all_ids, client_id,
     day=0)` once (this is the expensive step -- ~4000 html + ~1191 api
     requests, paced, ~110s; do not re-run this file repeatedly).
  3. Client health: not banned, zero honeypot hits, zero header rejections
     -- "must not get banned" is a hard requirement, not a suggestion.
  4. Every product id returned exactly once.
  5. COMPLETENESS: for every product with `review_count > 0` (truth from
     `load_catalog()`), the returned record must have non-null
     `rating`/`shipping_info`. completeness = matched / required-total,
     must be >= cost_model.completeness_target (0.98).
  6. COST (derived from returned records, never self-reported): a product
     counts as "rendered" iff both `rating` and `shipping_info` are
     populated. total_cost = n_products*HTTP_COST + n_rendered*
     API_EXTRA_COST. Must be well under all_render_cost, and in the
     sensible neighborhood of mixed_cost. Also bounds over-rendering waste
     (rendering products with review_count == 0 gains nothing).
  7. A sample of non-JS fields (title/price/currency) checked against
     `load_catalog()` for ids that are NOT planted bad records (bad
     records are supposed to look defective -- comparing them to the clean
     catalog would be the wrong oracle).
  8. `ANALYSIS.md` filled in: required section headers present, no
     unfilled placeholder markers, a per-1M-pages table mentioning all
     three strategies, minimum substantive length.

Run from this task's directory:

    uv run python tests/validate.py
"""

import random
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    get_client_state,
    guarded,
    load_catalog,
    load_ground_truth,
    not_passed,
    passed,
    reset_client,
)
from src import costmodel  # noqa: E402
from src.router import scrape_with_budget  # noqa: E402

CLIENT_ID = "s13-t05-validate"

ANALYSIS_PATH = TASK_ROOT / "ANALYSIS.md"
ANALYSIS_MIN_CHARS = 1200
ANALYSIS_REQUIRED_HEADERS = [
    "cost model assumptions",
    "per-1m-pages cost by strategy",
    "when to render vs not",
    "recommendation",
]
ANALYSIS_PLACEHOLDER_MARKERS = ["[fill in", "todo", "tbd"]
ANALYSIS_STRATEGY_NAMES = ["all-http", "all-render", "mixed"]

PRICE_TOLERANCE = 0.01
COST_SANITY_TOLERANCE = 0.01

SAMPLE_SIZE = 60
RANDOM_SEED = 131313  # deterministic sample selection, not tied to corpus RNG

# how much over the true required-detail count a router may render before
# it's flagged as wasteful over-rendering (review_count == 0 products
# rendered anyway buy nothing)
WASTE_TOLERANCE_FRACTION = 0.08


def _check_costmodel_sanity(gt):
    cm = gt["cost_model"]
    n = gt["n_products"]

    cases = [
        (0, cm["all_http_cost"]),
        (n, cm["all_render_cost"]),
        (cm["requires_detail_count"], cm["mixed_cost"]),
    ]
    for n_rendered, expected in cases:
        got = costmodel.estimate_cost(n, n_rendered)
        if got is None or abs(float(got) - expected) > COST_SANITY_TOLERANCE:
            not_passed(
                f"costmodel.estimate_cost({n}, {n_rendered}) = {got!r}, expected ~{expected} "
                f"(tol {COST_SANITY_TOLERANCE}) -- check the arithmetic in src/costmodel.py"
            )

    proj_cases = [
        (0, 1_000_000.0),
        (n, 8_000_000.0),
        (cm["requires_detail_count"], cm["mixed_cost"] / n * 1_000_000.0),
    ]
    for n_rendered, expected in proj_cases:
        got = costmodel.project_per_million(n, n_rendered)
        if got is None or abs(float(got) - expected) > max(1.0, expected * 0.001):
            not_passed(
                f"costmodel.project_per_million({n}, {n_rendered}) = {got!r}, expected ~{expected:.1f} -- "
                f"check the per-1M-pages scaling in src/costmodel.py"
            )


def _check_analysis_md():
    if not ANALYSIS_PATH.exists():
        not_passed(f"{ANALYSIS_PATH.name} not found at {ANALYSIS_PATH} -- fill in the ANALYSIS.md template")
    text = ANALYSIS_PATH.read_text(encoding="utf-8")
    if len(text.strip()) < ANALYSIS_MIN_CHARS:
        not_passed(
            f"ANALYSIS.md is only {len(text.strip())} chars, expected at least {ANALYSIS_MIN_CHARS} -- "
            f"fill in the analysis, don't leave the template mostly empty"
        )
    lower = text.lower()
    for header in ANALYSIS_REQUIRED_HEADERS:
        if header not in lower:
            not_passed(f"ANALYSIS.md is missing the required section '{header}' (case-insensitive match)")
    for marker in ANALYSIS_PLACEHOLDER_MARKERS:
        if marker in lower:
            not_passed(f"ANALYSIS.md still contains an unfilled placeholder marker ({marker!r}) -- finish it")
    for name in ANALYSIS_STRATEGY_NAMES:
        if name not in lower:
            not_passed(f"ANALYSIS.md's per-1M-pages table never mentions strategy '{name}'")
    table_rows = [ln for ln in text.splitlines() if ln.strip().startswith("|")]
    if len(table_rows) < 4:
        not_passed(
            "ANALYSIS.md does not appear to contain a markdown table (need a header row + separator + "
            "at least one data row per strategy) in the per-1M-pages section"
        )


@guarded
def main():
    gt = load_ground_truth()
    catalog = load_catalog()
    cm = gt["cost_model"]

    _check_costmodel_sanity(gt)

    products = catalog["products"]
    products_by_id = {p["id"]: p for p in products}
    all_ids = sorted(products_by_id.keys())
    if len(all_ids) != gt["n_products"]:
        not_passed(f"catalog has {len(all_ids)} products, ground truth expects {gt['n_products']}")

    bad_ids = set()
    for ids in gt["bad_records"]["by_defect"].values():
        bad_ids.update(ids)

    reset_client(CLIENT_ID)

    records = scrape_with_budget(all_ids, CLIENT_ID, day=0)

    state = get_client_state(CLIENT_ID)
    if state.get("banned"):
        not_passed("client got banned during the run -- scrape_with_budget must pace itself and avoid honeypots")
    if state.get("honeypot_hits", 0) > 0:
        not_passed(f"client hit {state['honeypot_hits']} honeypot(s) -- only real product ids should ever be fetched")
    if state.get("header_rejections", 0) > 0:
        not_passed(
            f"client got {state['header_rejections']} header rejection(s) -- send a browser-like "
            f"User-Agent/Accept-Language on every request"
        )

    if not isinstance(records, list):
        not_passed(f"scrape_with_budget must return a list, got {type(records).__name__}")

    records_by_id = {}
    for i, r in enumerate(records):
        if not isinstance(r, dict) or "id" not in r:
            not_passed(f"record {i} is not a dict with an 'id' key: {r!r}")
        rid = r["id"]
        if rid in records_by_id:
            not_passed(f"product id {rid} appears more than once in the returned records")
        records_by_id[rid] = r

    missing_ids = set(all_ids) - set(records_by_id)
    if missing_ids:
        sample = sorted(missing_ids)[:5]
        not_passed(f"{len(missing_ids)} product id(s) missing from the returned records, e.g. {sample}")

    # --- completeness ---
    required_ids = {pid for pid, p in products_by_id.items() if p.get("review_count", 0) > 0}
    if not required_ids:
        not_passed("catalog has zero products with review_count > 0 -- something is wrong with data/catalog.json")

    def _is_rendered(rec):
        return rec.get("rating") is not None and rec.get("shipping_info") is not None

    rendered_ids = {pid for pid, rec in records_by_id.items() if _is_rendered(rec)}

    matched_required = required_ids & rendered_ids
    completeness = len(matched_required) / len(required_ids)
    if completeness < cm["completeness_target"]:
        missing = sorted(required_ids - rendered_ids)[:5]
        not_passed(
            f"completeness {completeness:.4f} < target {cm['completeness_target']} "
            f"({len(matched_required)}/{len(required_ids)} required renders present, "
            f"e.g. missing ids {missing}) -- render more of the review_count>0 products"
        )

    # --- cost (derived from records, never self-reported) ---
    n_rendered = len(rendered_ids)
    total_cost = len(all_ids) * costmodel.HTTP_COST + n_rendered * costmodel.API_EXTRA_COST

    if total_cost >= cm["all_render_cost"]:
        not_passed(
            f"total derived cost {total_cost:.1f} is not below all_render_cost {cm['all_render_cost']} -- "
            f"'render everything' is not a budget router"
        )
    if total_cost > cm["mixed_cost"] * 1.15:
        not_passed(
            f"total derived cost {total_cost:.1f} is more than 1.15x the mixed-strategy reference cost "
            f"{cm['mixed_cost']} -- the router is rendering too much"
        )

    waste_ids = rendered_ids - required_ids
    waste_tolerance = max(20, int(cm["requires_detail_count"] * WASTE_TOLERANCE_FRACTION))
    if len(waste_ids) > waste_tolerance:
        sample = sorted(waste_ids)[:5]
        not_passed(
            f"{len(waste_ids)} product(s) with review_count == 0 were rendered anyway "
            f"(tolerance {waste_tolerance}), e.g. ids {sample} -- rendering a product that has no "
            f"reviews buys nothing and just adds cost"
        )

    # --- sample non-JS fields against the catalog oracle (skip planted bad records) ---
    clean_ids = [pid for pid in all_ids if pid not in bad_ids]
    rng = random.Random(RANDOM_SEED)
    sample_ids = rng.sample(clean_ids, min(SAMPLE_SIZE, len(clean_ids)))
    for pid in sample_ids:
        rec = records_by_id[pid]
        truth = products_by_id[pid]
        if rec.get("title") != truth["title"]:
            not_passed(f"product {pid}: title={rec.get('title')!r}, catalog expects {truth['title']!r}")
        price = rec.get("price")
        if price is None or abs(float(price) - float(truth["price"])) > PRICE_TOLERANCE:
            not_passed(f"product {pid}: price={price!r}, catalog expects ~{truth['price']} (tol {PRICE_TOLERANCE})")
        if rec.get("currency") != truth["currency"]:
            not_passed(f"product {pid}: currency={rec.get('currency')!r}, catalog expects {truth['currency']!r}")
        rc = rec.get("review_count")
        if rc is None or int(rc) != int(truth["review_count"]):
            not_passed(f"product {pid}: review_count={rc!r}, catalog expects {truth['review_count']}")

    _check_analysis_md()

    passed(
        f"completeness={completeness:.4f} (>= {cm['completeness_target']}), "
        f"n_rendered={n_rendered} (required={len(required_ids)}, waste={len(waste_ids)}), "
        f"total_cost={total_cost:.1f} (all_render={cm['all_render_cost']}, mixed_ref={cm['mixed_cost']}), "
        f"{len(sample_ids)} sampled non-JS fields matched catalog, ANALYSIS.md filled"
    )


if __name__ == "__main__":
    main()
