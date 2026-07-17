"""Validator for 13-scraping-at-scale task 04 -- markup-resilience.

Independent of `load_catalog()`'s shape assumptions in one important sense:
it drives the LIVE target directly (via `harness.TargetClient`, a plain
HTTP client with no parsing of its own) to fetch real HTML for a sample of
products under all 4 explicit markup versions, then compares the learner's
`extract_product(html, product_id)` output against `data/catalog.json`'s
true field values -- it never trusts anything the learner's own code
reports about itself.

What it checks:

  1. Selects a SAMPLE of CLEAN product ids (excluding every id in ground
     truth's `bad_records.by_defect` -- this task is about markup-encoding
     resilience, not the malformed-field data-quality contracts task 02
     covers) spread across `id % 4 == 0, 1, 2, 3` so the sample includes
     products whose *default* rendering would be each of the 4 versions,
     though every version is fetched explicitly via `?v=` for every id
     regardless of that default.
  2. For each sampled id, fetches `/product/{id}?v={v}&day=0` for v in
     1..4 (day=0 is the undisturbed baseline -- catalog.json IS the ground
     truth at day 0, no change-day overlay to replay) and calls the
     learner's `extract_product`.
  3. Scores each of the 7 required fields (title, price, currency,
     in_stock, seller_name, review_count, description) as correct/
     incorrect against the catalog record -- a missing (None) field counts
     as incorrect, so completeness and correctness collapse into one
     combined per-field score (a chain that returns None for a field it
     can't find scores identically to one that gets it wrong).
  4. Aggregates a per-version score (correct fields / total fields checked,
     over all sampled records for that version) and an overall score
     across all 4 versions combined. PASSES only if the overall score is
     >= 0.98 AND no single version's score is below 0.95 -- a chain that
     handles 3 of 4 encodings well and silently fails the 4th (e.g. never
     looks inside a `<script type="application/ld+json">` block) fails the
     per-version floor even if its overall average looks fine.

Fetches are paced (a fixed sleep between requests, well under the target's
`refill_per_sec=50`) to stay polite -- this validator does not exercise
task 01's rate-limit-avoidance lesson, it just needs the target to answer
normally throughout.

Run from the MODULE ROOT (13-scraping-at-scale/), not this task directory:

    uv run python 04-markup-resilience/tests/validate.py
"""

import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    TargetClient,
    guarded,
    load_catalog,
    load_ground_truth,
    not_passed,
    passed,
)
from src.extract import extract_product  # noqa: E402

VERSIONS = (1, 2, 3, 4)
SAMPLE_PER_RESIDUE = 50  # -> up to 200 products x 4 versions = 800 fetches
REQUEST_PACE_SEC = 0.05  # ~20 req/s, comfortably under the 50/s token refill

PRICE_TOL = 0.01
OVERALL_MIN = 0.98
PER_VERSION_MIN = 0.95
DESC_PREFIX_MIN_RATIO = 0.6  # a normalized prefix must cover >= 60% of the true description

FIELDS = ("title", "price", "currency", "in_stock", "seller_name", "review_count", "description")


def _bad_ids(ground_truth):
    ids = set()
    for defect_ids in ground_truth["bad_records"]["by_defect"].values():
        ids.update(int(i) for i in defect_ids)
    return ids


def _sample_ids(catalog, bad_ids):
    """Up to SAMPLE_PER_RESIDUE clean ids per id%4 residue class, evenly
    strided across each residue's id range (spreads the sample across
    categories too, since category assignment is independent of id order)."""
    all_ids = sorted(p["id"] for p in catalog["products"])
    clean_ids = [pid for pid in all_ids if pid not in bad_ids]
    by_residue = {0: [], 1: [], 2: [], 3: []}
    for pid in clean_ids:
        by_residue[pid % 4].append(pid)

    sample = []
    for r in (0, 1, 2, 3):
        group = by_residue[r]
        if not group:
            not_passed(f"no clean product ids with id%4=={r} in the catalog -- catalog/ground-truth mismatch?")
        step = max(1, len(group) // SAMPLE_PER_RESIDUE)
        sample.extend(group[::step][:SAMPLE_PER_RESIDUE])
    return sorted(set(sample))


def _normalize_ws(s):
    return " ".join((s or "").split())


def _description_ok(extracted, expected):
    e = _normalize_ws(extracted)
    x = _normalize_ws(expected)
    if not e or not x:
        return False
    if e == x:
        return True
    return x.startswith(e) and len(e) >= DESC_PREFIX_MIN_RATIO * len(x)


def _score_record(extracted, truth):
    """Return {field: bool correct} for one extracted record vs. its
    catalog truth. A missing/wrong-typed field scores False, never raises."""
    if not isinstance(extracted, dict):
        return {f: False for f in FIELDS}

    scores = {}
    scores["title"] = extracted.get("title") == truth["title"]

    price = extracted.get("price")
    try:
        scores["price"] = price is not None and abs(float(price) - float(truth["price"])) < PRICE_TOL
    except (TypeError, ValueError):
        scores["price"] = False

    scores["currency"] = extracted.get("currency") == truth["currency"]

    in_stock = extracted.get("in_stock")
    scores["in_stock"] = isinstance(in_stock, bool) and in_stock == truth["in_stock"]

    scores["seller_name"] = extracted.get("seller_name") == truth["seller_name"]

    rc = extracted.get("review_count")
    try:
        scores["review_count"] = rc is not None and not isinstance(rc, bool) and int(rc) == int(truth["review_count"])
    except (TypeError, ValueError):
        scores["review_count"] = False

    scores["description"] = _description_ok(extracted.get("description"), truth["description"])
    return scores


def _fetch_html(client, pid, v):
    r = client.get(f"/product/{pid}", params={"v": v, "day": 0})
    if r.status_code != 200:
        not_passed(
            f"GET /product/{pid}?v={v}&day=0 returned HTTP {r.status_code} "
            f"(target unreachable, banned client, or unexpected id) -- body: {r.text[:200]!r}"
        )
    return r.text


@guarded
def main():
    catalog = load_catalog()
    ground_truth = load_ground_truth()
    bad_ids = _bad_ids(ground_truth)
    products_by_id = {p["id"]: p for p in catalog["products"]}

    sample_ids = _sample_ids(catalog, bad_ids)

    per_version = {
        v: {f: [0, 0] for f in FIELDS}  # field -> [correct, total]
        for v in VERSIONS
    }
    # First failing (version, field) example per field, for a precise message.
    first_failure = {}

    with TargetClient(client_id="s13-t04-markup-resilience-validator") as client:
        for pid in sample_ids:
            truth = products_by_id[pid]
            for v in VERSIONS:
                html = _fetch_html(client, pid, v)
                time.sleep(REQUEST_PACE_SEC)

                try:
                    extracted = extract_product(html, pid)
                except NotImplementedError:
                    raise
                except Exception as e:
                    not_passed(f"extract_product raised {type(e).__name__}: {e} (product {pid}, v={v})")

                scores = _score_record(extracted, truth)
                for f, ok in scores.items():
                    per_version[v][f][1] += 1
                    if ok:
                        per_version[v][f][0] += 1
                    elif (v, f) not in first_failure:
                        got = extracted.get(f) if isinstance(extracted, dict) else extracted
                        first_failure[(v, f)] = (pid, got, truth.get(f))

    # --- aggregate ---
    per_version_score = {}
    overall_correct = 0
    overall_total = 0
    for v in VERSIONS:
        v_correct = sum(c for c, _ in per_version[v].values())
        v_total = sum(t for _, t in per_version[v].values())
        per_version_score[v] = v_correct / v_total if v_total else 0.0
        overall_correct += v_correct
        overall_total += v_total

    overall_score = overall_correct / overall_total if overall_total else 0.0

    breakdown = ", ".join(f"v{v}={per_version_score[v]:.3f}" for v in VERSIONS)

    worst_versions = [v for v in VERSIONS if per_version_score[v] < PER_VERSION_MIN]
    if worst_versions:
        v = min(worst_versions, key=lambda vv: per_version_score[vv])
        # name the worst field within that version
        worst_field = min(FIELDS, key=lambda f: per_version[v][f][0] / per_version[v][f][1])
        f_correct, f_total = per_version[v][worst_field]
        example = first_failure.get((v, worst_field))
        example_msg = f" e.g. product {example[0]}: got {example[1]!r}, expected {example[2]!r}." if example else ""
        not_passed(
            f"markup version v{v} scored {per_version_score[v]:.3f} (< floor {PER_VERSION_MIN}); "
            f"weakest field '{worst_field}' {f_correct}/{f_total} correct on that version.{example_msg} "
            f"Per-version breakdown: {breakdown}. "
            f"This usually means one whole encoding's field is never being reached by any fallback "
            f"(check the microdata itemprop / JSON-LD script / __DATA__ island paths)."
        )

    if overall_score < OVERALL_MIN:
        v = min(VERSIONS, key=lambda vv: per_version_score[vv])
        worst_field = min(FIELDS, key=lambda f: per_version[v][f][0] / per_version[v][f][1])
        not_passed(
            f"overall extraction score {overall_score:.3f} (< {OVERALL_MIN}) across "
            f"{len(sample_ids)} products x {len(VERSIONS)} versions ({overall_correct}/{overall_total} "
            f"field checks correct). Per-version breakdown: {breakdown}. Weakest: v{v}/{worst_field}."
        )

    passed(
        f"{len(sample_ids)} products x {len(VERSIONS)} versions ({overall_total} field checks), "
        f"overall {overall_score:.3f} (>= {OVERALL_MIN}). Per-version: {breakdown} (floor {PER_VERSION_MIN})."
    )


if __name__ == "__main__":
    main()
