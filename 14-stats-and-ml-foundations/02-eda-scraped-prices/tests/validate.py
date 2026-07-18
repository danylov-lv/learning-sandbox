"""Validator for 14-stats-and-ml-foundations task 02 -- eda-scraped-prices.

Three things must be true, checked in this order:

  1. `summarize_pandas(load_observations())` and `summarize_polars()` agree
     with each other -- the pandas-vs-polars taste this task is about. Two
     independent codebases, same question, same answer.
  2. The facts themselves are correct. `n_obs`, `n_products`, and
     `per_category_count` are graded against `load_ground_truth()` (those
     three are computed over ALL rows with no "valid price" filtering, so
     they line up with the committed ground truth exactly). The remaining
     facts (`valid_price_median`, `valid_price_mean`, `nan_price_rate`,
     `per_source_site_count`, `busiest_day`) depend on this task's specific
     "valid price" definition (price not NaN, price > 0, currency == "USD"
     -- see src/eda.py's module docstring), which is intentionally simpler
     than the defect-aware definition used elsewhere in this module (a
     later task teaches telling a parsing artifact from a genuine value).
     Because of that, they are graded against a reference this validator
     recomputes independently from `load_observations()`, not against
     `ground-truth.json`'s stricter `valid_price_*` fields.
  3. `make_figure(df)` returns a matplotlib Figure with actual drawn
     content (`require_figure`).

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
    check_close,
    guarded,
    load_ground_truth,
    load_observations,
    not_passed,
    passed,
    require_figure,
)
from src.eda import make_figure, summarize_pandas, summarize_polars  # noqa: E402

REQUIRED_KEYS = [
    "n_obs",
    "n_products",
    "per_category_count",
    "valid_price_median",
    "valid_price_mean",
    "nan_price_rate",
    "per_source_site_count",
    "busiest_day",
]

DICT_KEYS = {"per_category_count", "per_source_site_count"}
NUMERIC_KEYS = {"n_obs", "n_products", "valid_price_median", "valid_price_mean", "nan_price_rate"}
STRING_KEYS = {"busiest_day"}


def check_shape(name, d):
    if not isinstance(d, dict):
        return False, f"{name}() must return a dict, got {type(d).__name__}"
    missing = [k for k in REQUIRED_KEYS if k not in d]
    if missing:
        return False, f"{name}() result is missing key(s): {missing}"
    return True, ""


def check_dicts_equal(name, got, want, rel=1e-6, abs_=1e-9):
    got_keys, want_keys = set(got), set(want)
    if got_keys != want_keys:
        return False, (
            f"{name}: key sets differ -- got {sorted(got_keys)}, want {sorted(want_keys)}"
        )
    for k in sorted(want_keys):
        gv, wv = got[k], want[k]
        if not check_close(f"{name}[{k!r}]", float(gv), float(wv), rel=rel, abs_=abs_)[0]:
            return False, f"{name}[{k!r}]: got {gv!r}, want {wv!r}"
    return True, ""


def check_agreement(pandas_result, polars_result):
    for key in REQUIRED_KEYS:
        got, want = pandas_result[key], polars_result[key]
        if key in DICT_KEYS:
            ok, msg = check_dicts_equal(key, got, want)
            if not ok:
                return False, f"pandas vs polars disagree on {msg}"
        elif key in STRING_KEYS:
            if str(got) != str(want):
                return False, (
                    f"pandas vs polars disagree on '{key}': "
                    f"pandas={got!r}, polars={want!r}"
                )
        else:
            ok, msg = check_close(key, float(got), float(want), rel=1e-6, abs_=1e-6)
            if not ok:
                return False, f"pandas vs polars disagree: {msg}"
    return True, ""


# --------------------------------------------------------------------------
# Independent reference (mirrors the "valid price" definition documented in
# src/eda.py: price not NaN, price > 0, currency == "USD")
# --------------------------------------------------------------------------

def build_reference(df):
    valid_mask = df["price"].notna() & (df["price"] > 0) & (df["currency"] == "USD")
    valid_prices = df.loc[valid_mask, "price"]

    busiest_day = df["scraped_at"].dt.date.value_counts().idxmax()

    return {
        "n_obs": len(df),
        "n_products": df["product_id"].nunique(),
        "per_category_count": {str(k): int(v) for k, v in df["category"].value_counts().items()},
        "valid_price_median": float(valid_prices.median()),
        "valid_price_mean": float(valid_prices.mean()),
        "nan_price_rate": float(df["price"].isna().mean()),
        "per_source_site_count": {str(k): int(v) for k, v in df["source_site"].value_counts().items()},
        "busiest_day": str(busiest_day),
    }


@guarded
def main():
    df = load_observations()

    pandas_result = summarize_pandas(df)
    ok, msg = check_shape("summarize_pandas", pandas_result)
    if not ok:
        not_passed(msg)

    polars_result = summarize_polars()
    ok, msg = check_shape("summarize_polars", polars_result)
    if not ok:
        not_passed(msg)

    ok, msg = check_agreement(pandas_result, polars_result)
    if not ok:
        not_passed(msg)

    reference = build_reference(df)

    gt = load_ground_truth()
    for key, gt_key in (("n_obs", "n_obs"), ("n_products", "n_products")):
        ok, msg = check_close(key, float(pandas_result[key]), float(gt[gt_key]), rel=1e-9, abs_=1e-9)
        if not ok:
            not_passed(msg)

    ok, msg = check_dicts_equal("per_category_count", pandas_result["per_category_count"], gt["per_category_count"])
    if not ok:
        not_passed(msg)

    for key in ("valid_price_median", "valid_price_mean", "nan_price_rate"):
        ok, msg = check_close(key, float(pandas_result[key]), reference[key], rel=1e-6, abs_=1e-6)
        if not ok:
            not_passed(msg)

    ok, msg = check_dicts_equal("per_source_site_count", pandas_result["per_source_site_count"], reference["per_source_site_count"])
    if not ok:
        not_passed(msg)

    if str(pandas_result["busiest_day"]) != reference["busiest_day"]:
        not_passed(
            f"busiest_day: got {pandas_result['busiest_day']!r}, "
            f"want {reference['busiest_day']!r}"
        )

    fig = make_figure(df)
    ok, msg = require_figure(fig)
    if not ok:
        not_passed(msg)

    passed(
        f"n_obs={pandas_result['n_obs']}, n_products={pandas_result['n_products']}, "
        f"valid_price_median={pandas_result['valid_price_median']:.2f}, "
        f"nan_price_rate={pandas_result['nan_price_rate']:.4f}, "
        f"busiest_day={pandas_result['busiest_day']}; pandas/polars agree; figure ok"
    )


if __name__ == "__main__":
    main()
