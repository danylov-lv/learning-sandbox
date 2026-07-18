"""Validator for 14-stats-and-ml-foundations task 10 --
sklearn-pipeline-leakage.

Loads the shared dataset and calls the learner's three functions in
`src/leakage.py`:

1. `build_pipeline()` -- checked structurally: must return an actual
   `sklearn.pipeline.Pipeline` with at least 2 steps (a preprocessing step
   feeding a final regressor).
2. `leaky_holdout_r2(df)` -- the WRONG way to add a target-encoded feature
   (computed over the whole dataset before splitting). Expected to be
   inflated.
3. `correct_holdout_r2(df)` -- the RIGHT way (computed from train rows
   only, after splitting). Expected to be the honest number.

Two thresholds, both measured empirically while authoring this task
(Ridge and HistGradientBoostingRegressor both tested; see NOTES/`
.authoring` for the numbers) and set with generous headroom below what a
correct solution achieves, so a reasonable choice of regressor or minor
implementation differences don't cause a false NOT PASSED:

  - `LEAK_GAP`: `leaky_holdout_r2 - correct_holdout_r2` must be at least
    this large -- the leak must clearly and substantially inflate R^2, not
    just nudge it.
  - `MIN_HONEST_R2`: `correct_holdout_r2` must be at least this large --
    the honest model should still show real signal (price is strongly
    category-driven in this dataset), not near-zero or negative.

Run from the module root:

    uv run python 10-sklearn-pipeline-leakage/tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, load_observations, not_passed, passed  # noqa: E402
from src.leakage import build_pipeline, correct_holdout_r2, leaky_holdout_r2  # noqa: E402

# Measured while authoring (Ridge: leaky~0.526, correct~0.320, gap~0.206;
# HistGradientBoostingRegressor: leaky~0.517, correct~0.321, gap~0.196).
# Thresholds set with roughly 2x headroom below those measurements.
LEAK_GAP = 0.10
MIN_HONEST_R2 = 0.15


def check_pipeline(pipe):
    from sklearn.pipeline import Pipeline

    if not isinstance(pipe, Pipeline):
        return False, f"build_pipeline() must return an sklearn Pipeline, got {type(pipe).__name__}"
    if len(pipe.steps) < 2:
        return False, (
            f"build_pipeline() returned a Pipeline with only {len(pipe.steps)} step(s) -- "
            f"expected at least a preprocessing step (ColumnTransformer) feeding a regressor"
        )
    return True, ""


def check_r2(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, f"{name} must return a float, got {type(value).__name__}: {value!r}"
    value = float(value)
    if not (value == value) or value in (float("inf"), float("-inf")):
        return False, f"{name} returned a non-finite value: {value!r}"
    if value > 1.0 + 1e-6:
        return False, f"{name} returned {value!r}, which is above the max possible R^2 of 1.0 -- check the score computation"
    return True, ""


@guarded
def main():
    df = load_observations()

    pipe = build_pipeline()
    ok, msg = check_pipeline(pipe)
    if not ok:
        not_passed(msg)

    leaky = leaky_holdout_r2(df)
    ok, msg = check_r2("leaky_holdout_r2", leaky)
    if not ok:
        not_passed(msg)
    leaky = float(leaky)

    correct = correct_holdout_r2(df)
    ok, msg = check_r2("correct_holdout_r2", correct)
    if not ok:
        not_passed(msg)
    correct = float(correct)

    gap = leaky - correct

    if gap < LEAK_GAP:
        not_passed(
            f"leaky_holdout_r2 ({leaky:.4f}) does not clearly exceed correct_holdout_r2 "
            f"({correct:.4f}) -- gap is {gap:.4f}, need >= {LEAK_GAP}. Check that "
            f"leaky_holdout_r2 computes product_mean_logprice over the WHOLE dataset "
            f"before splitting, and that correct_holdout_r2 computes it from TRAIN rows "
            f"only after splitting"
        )

    if correct < MIN_HONEST_R2:
        not_passed(
            f"correct_holdout_r2 ({correct:.4f}) is below {MIN_HONEST_R2} -- the honest "
            f"model should still show real signal (price is strongly category-driven in "
            f"this dataset). Check build_pipeline()'s feature set and that the fit/score "
            f"are being computed on the right rows"
        )

    passed(
        f"leaky R^2={leaky:.4f}, honest R^2={correct:.4f}, gap={gap:.4f} "
        f"(required gap >= {LEAK_GAP}, honest R^2 >= {MIN_HONEST_R2})"
    )


if __name__ == "__main__":
    main()
