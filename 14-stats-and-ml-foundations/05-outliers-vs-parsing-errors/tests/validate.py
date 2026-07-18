"""Validator for 14-stats-and-ml-foundations task 05 --
outliers-vs-parsing-errors.

Reconstructs the dataset's hidden ground truth by calling
`generate.build_observations(seed, n_obs)` directly (never from a hidden
file -- see .authoring/design.md), then grades the learner's
`classify_prices(df)` from `src/quality.py` against it:

- `negative` / `zero` / `nan` parsing errors must be caught with 100%
  recall -- these are unambiguous.
- `missing_decimal` must be caught with recall >= MISSING_DECIMAL_MIN_RECALL
  (a few borderline misses in the hardest category are tolerated).
- CRITICAL gate: zero genuine outliers may appear in the learner's
  `parsing_error_ids` -- flagging a real, expensive product as a parsing
  error fails the task outright regardless of how good the recall numbers
  are.
- Overall precision of the flagged set against the true defect set must
  stay >= MIN_PRECISION, so the rule isn't quarantining ordinary mid-range
  prices "just in case."
- `make_figure(df)` must return a Figure with real drawn content
  (`harness.common.require_figure`).

Run from this task's directory:

    uv run python tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    guarded,
    load_ground_truth,
    load_observations,
    not_passed,
    passed,
    require_figure,
)

# --------------------------------------------------------------------------
# Grading thresholds -- chosen and verified against a reference method (see
# .authoring/design.md): impossible values (<=0 / NaN) free; missing-decimal
# via a per-category robust (median/MAD, log-scale) "does price/100 rejoin
# the pack" signature plus a whole-dollar check. That reference clears every
# bar below with headroom (missing_decimal recall ~0.99, 0 genuine-outlier
# false positives, precision 1.0), while a naive "flag anything > 3 std devs
# from the mean" rule -- even computed per-category on a log scale -- either
# misses most missing_decimal rows or drags several genuine outliers into
# the flagged set, failing the zero-false-positive gate below.
# --------------------------------------------------------------------------

IMPOSSIBLE_KINDS = ["negative", "zero", "nan"]
IMPOSSIBLE_MIN_RECALL = 1.0        # must catch every single one -- unambiguous
MISSING_DECIMAL_MIN_RECALL = 0.95  # allow a few borderline misses
MAX_GENUINE_OUTLIER_FP = 0         # zero tolerance -- the whole point of the task
MIN_PRECISION = 0.98               # flagged set must be almost entirely real defects


@guarded
def main():
    gt = load_ground_truth()
    seed = gt["seed"]
    n_obs = gt["n_obs"]

    from generate import build_observations  # noqa: E402

    _, labels = build_observations(seed, n_obs)

    df = load_observations()
    if len(df) != n_obs:
        not_passed(
            f"data/observations.parquet has {len(df)} rows but ground-truth.json "
            f"reports n_obs={n_obs} -- regenerate with `uv run python generate.py` "
            f"(and make sure SCALE matches what ground-truth.json was built with)"
        )

    try:
        from src.quality import classify_prices, make_figure
    except ImportError as e:
        not_passed(f"could not import src/quality.py: {e}")

    result = classify_prices(df)

    if not isinstance(result, dict):
        not_passed(f"classify_prices(df) must return a dict, got {type(result).__name__}")
    missing_keys = {"parsing_error_ids", "kept_ids"} - set(result)
    if missing_keys:
        not_passed(f"classify_prices(df) return value missing key(s): {sorted(missing_keys)}")

    try:
        parsing_error_ids = {int(x) for x in result["parsing_error_ids"]}
        kept_ids = {int(x) for x in result["kept_ids"]}
    except (TypeError, ValueError) as e:
        not_passed(f"parsing_error_ids / kept_ids must be iterables of int-like obs_id values: {e}")

    all_ids = {int(x) for x in df["obs_id"]}

    overlap = parsing_error_ids & kept_ids
    if overlap:
        not_passed(
            f"{len(overlap)} obs_id appear in BOTH parsing_error_ids and kept_ids "
            f"(e.g. {sorted(overlap)[:5]}) -- the two sets must be disjoint"
        )

    union = parsing_error_ids | kept_ids
    missing_from_union = all_ids - union
    extra_in_union = union - all_ids
    if missing_from_union:
        not_passed(
            f"{len(missing_from_union)} obs_id from df are in neither set "
            f"(e.g. {sorted(missing_from_union)[:5]}) -- every row must be classified"
        )
    if extra_in_union:
        not_passed(
            f"{len(extra_in_union)} obs_id in your result don't correspond to any row "
            f"in df (e.g. {sorted(extra_in_union)[:5]})"
        )

    # --------------------------------------------------------------------
    # Reconstruct ground truth, obs_id-aligned (obs_id = position + 1).
    # --------------------------------------------------------------------
    defect_mask = labels["defect_mask"]
    defect_kind = labels["defect_kind"]
    genuine_outlier_mask = labels["genuine_outlier_mask"]
    obs_id_arr = list(range(1, n_obs + 1))

    def ids_where(mask):
        return {obs_id_arr[i] for i, flag in enumerate(mask) if flag}

    recalls = {}
    for kind in IMPOSSIBLE_KINDS:
        true_ids = ids_where(defect_kind == kind)
        if not true_ids:
            continue
        caught = parsing_error_ids & true_ids
        recall = len(caught) / len(true_ids)
        recalls[kind] = recall
        if recall < IMPOSSIBLE_MIN_RECALL:
            not_passed(
                f"{kind} recall {recall:.4f} is below the required {IMPOSSIBLE_MIN_RECALL:.2f} "
                f"({len(true_ids) - len(caught)} of {len(true_ids)} missed) -- {kind} prices are "
                f"unambiguous parsing errors, there's no excuse for missing one"
            )

    md_true_ids = ids_where(defect_kind == "missing_decimal")
    md_recall = 0.0
    if md_true_ids:
        md_caught = parsing_error_ids & md_true_ids
        md_recall = len(md_caught) / len(md_true_ids)
        recalls["missing_decimal"] = md_recall
        if md_recall < MISSING_DECIMAL_MIN_RECALL:
            not_passed(
                f"missing_decimal recall {md_recall:.4f} is below the required "
                f"{MISSING_DECIMAL_MIN_RECALL:.2f} ({len(md_true_ids) - len(md_caught)} of "
                f"{len(md_true_ids)} missed) -- refine the divide-by-100 signature test "
                f"(see hint-2/hint-3)"
            )

    genuine_outlier_ids = ids_where(genuine_outlier_mask)
    fp_genuine = parsing_error_ids & genuine_outlier_ids
    n_fp_genuine = len(fp_genuine)
    if n_fp_genuine > MAX_GENUINE_OUTLIER_FP:
        example = sorted(fp_genuine)[:5]
        not_passed(
            f"{n_fp_genuine} genuine outlier(s) ended up in parsing_error_ids "
            f"(e.g. obs_id {example}) -- flagging a real, expensive product as a "
            f"parsing error is exactly the mistake this task exists to catch; your "
            f"missing-decimal test is too aggressive (widen the 'plausible' band or "
            f"tighten the distance threshold -- see hint-3)"
        )

    true_defect_ids = ids_where(defect_mask)
    if parsing_error_ids:
        precision = len(parsing_error_ids & true_defect_ids) / len(parsing_error_ids)
    else:
        precision = 1.0
    if precision < MIN_PRECISION:
        n_wrong = len(parsing_error_ids - true_defect_ids)
        not_passed(
            f"precision {precision:.4f} is below the required {MIN_PRECISION:.2f} "
            f"({n_wrong} of {len(parsing_error_ids)} flagged rows are not actually "
            f"price defects) -- your rule is quarantining too much ordinary data"
        )

    fig = make_figure(df)
    ok, msg = require_figure(fig)
    if not ok:
        not_passed(f"make_figure: {msg}")

    recall_summary = ", ".join(f"{k}={v:.4f}" for k, v in recalls.items())
    passed(
        f"recalls: {recall_summary}; genuine-outlier FP={n_fp_genuine}; "
        f"precision={precision:.4f}"
    )


if __name__ == "__main__":
    main()
