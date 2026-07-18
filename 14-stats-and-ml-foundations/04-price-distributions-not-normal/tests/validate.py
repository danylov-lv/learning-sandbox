"""Validator for 14-stats-and-ml-foundations task 04 --
price-distributions-not-normal.

Loads the shared dataset, filters to "valid" prices exactly as defined for
this task (price not NaN, price > 0, currency == "USD"), then:

1. Sanity-gates the DATA itself: the raw valid-price distribution really is
   significantly non-normal (skewness clearly positive, normaltest p-value
   ~ 0). If this ever fails, the dataset changed underneath the task, not
   the learner's code.
2. Independently recomputes skewness / excess kurtosis / normaltest p-value
   via scipy (the same three calls documented in src/distributions.py) on
   both the raw and log-transformed prices, and grades the learner's
   `describe_distribution` and `log_makes_it_normal` against that reference
   within a float tolerance.
3. Checks the learner's `log_makes_it_normal` sets `log_is_more_normal` to
   True, and that True is what the independently-recomputed rule also
   produces (so a learner can't just hardcode True).
4. Checks `make_figure` returns a structurally real, >=2-axes figure with
   drawn content (require_figure).

Run from the module root:

    uv run python 04-price-distributions-not-normal/tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import check_close, guarded, load_observations, not_passed, passed, require_figure  # noqa: E402
from src.distributions import describe_distribution, log_makes_it_normal, make_figure  # noqa: E402

# Skewness collapses by more than a factor of 5 on the log scale; both
# normaltest p-values underflow to ~0.0 at this sample size (see
# distributions.py's log_makes_it_normal docstring for why).
SKEW_RATIO_THRESHOLD = 0.2

# Sanity gate on the data itself, not on the learner's code.
MIN_RAW_SKEWNESS = 5.0
MAX_RAW_NORMALTEST_PVALUE = 1e-6


def valid_prices(df):
    mask = df["price"].notna() & (df["price"] > 0) & (df["currency"] == "USD")
    return df.loc[mask, "price"].to_numpy(dtype=float)


def reference_describe(prices):
    from scipy import stats

    return {
        "skewness": float(stats.skew(prices)),
        "excess_kurtosis": float(stats.kurtosis(prices)),
        "normaltest_pvalue": float(stats.normaltest(prices).pvalue),
    }


def check_stats_dict(label, got, want, rel=1e-6):
    if not isinstance(got, dict):
        return False, f"{label}: expected a dict, got {type(got).__name__}"
    for key in ("skewness", "excess_kurtosis", "normaltest_pvalue"):
        if key not in got:
            return False, f"{label}: missing key {key!r}"
        ok, msg = check_close(f"{label}.{key}", got[key], want[key], rel=rel, abs_=1e-9)
        if not ok:
            return False, msg
    return True, ""


@guarded
def main():
    import numpy as np

    df = load_observations()
    prices = valid_prices(df)
    if len(prices) < 100:
        not_passed(f"only {len(prices)} valid USD prices found -- dataset looks wrong, re-run generate.py")

    ref_raw = reference_describe(prices)
    ref_log = reference_describe(np.log(prices))

    # --- sanity gate on the data --------------------------------------
    if ref_raw["skewness"] < MIN_RAW_SKEWNESS:
        not_passed(
            f"data sanity check failed: raw valid-price skewness {ref_raw['skewness']:.3f} "
            f"is not clearly positive/right-skewed (expected >= {MIN_RAW_SKEWNESS}) -- "
            f"dataset may have changed"
        )
    if ref_raw["normaltest_pvalue"] > MAX_RAW_NORMALTEST_PVALUE:
        not_passed(
            f"data sanity check failed: raw valid-price normaltest p-value "
            f"{ref_raw['normaltest_pvalue']!r} is not close to 0 (expected <= "
            f"{MAX_RAW_NORMALTEST_PVALUE}) -- dataset may have changed"
        )

    ref_log_is_more_normal = (
        abs(ref_log["skewness"]) < SKEW_RATIO_THRESHOLD * abs(ref_raw["skewness"])
        and ref_log["normaltest_pvalue"] >= ref_raw["normaltest_pvalue"]
    )
    if not ref_log_is_more_normal:
        not_passed(
            "internal reference check failed: the log transform does not satisfy the "
            "log_is_more_normal rule on this dataset -- this indicates a task/data mismatch, "
            "not a learner error"
        )

    # --- learner: describe_distribution --------------------------------
    got_raw = describe_distribution(prices)
    ok, msg = check_stats_dict("describe_distribution(prices)", got_raw, ref_raw)
    if not ok:
        not_passed(msg)

    got_log_direct = describe_distribution(np.log(prices))
    ok, msg = check_stats_dict("describe_distribution(log(prices))", got_log_direct, ref_log)
    if not ok:
        not_passed(msg)

    # --- learner: log_makes_it_normal -----------------------------------
    result = log_makes_it_normal(prices)
    if not isinstance(result, dict):
        not_passed(f"log_makes_it_normal: expected a dict, got {type(result).__name__}")
    for key in ("raw", "log", "log_is_more_normal"):
        if key not in result:
            not_passed(f"log_makes_it_normal: missing key {key!r}")

    ok, msg = check_stats_dict("log_makes_it_normal['raw']", result["raw"], ref_raw)
    if not ok:
        not_passed(msg)
    ok, msg = check_stats_dict("log_makes_it_normal['log']", result["log"], ref_log)
    if not ok:
        not_passed(msg)

    if not isinstance(result["log_is_more_normal"], (bool, np.bool_)):
        not_passed(
            f"log_makes_it_normal['log_is_more_normal']: expected a bool, "
            f"got {type(result['log_is_more_normal']).__name__}"
        )
    if bool(result["log_is_more_normal"]) is not True:
        not_passed(
            "log_makes_it_normal['log_is_more_normal'] is not True -- the log transform clearly "
            f"reduces skewness (raw {ref_raw['skewness']:.2f} -> log {ref_log['skewness']:.2f}) "
            "and does not worsen the normaltest p-value; re-check the rule in the docstring"
        )

    # --- learner: make_figure -------------------------------------------
    fig = make_figure(prices)
    ok, msg = require_figure(fig, min_axes=2)
    if not ok:
        not_passed(f"make_figure: {msg}")

    passed(
        f"raw skewness={ref_raw['skewness']:.2f} (p={ref_raw['normaltest_pvalue']:.3g}), "
        f"log skewness={ref_log['skewness']:.2f} (p={ref_log['normaltest_pvalue']:.3g})"
    )


if __name__ == "__main__":
    main()
