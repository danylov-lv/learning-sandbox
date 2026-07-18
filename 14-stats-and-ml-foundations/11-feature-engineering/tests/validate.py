"""Validator for 14-stats-and-ml-foundations task 11 --
feature-engineering.

Loads the shared observations dataset, computes:

    base_r2 = evaluate(baseline_features(df), df)
    eng_r2  = evaluate(engineered_features(df), df)

via the SAME fixed split (`baseline.make_split`, `SPLIT_SEED=42,
TEST_SIZE=0.2`) and the SAME fixed regressor (`baseline.evaluate`), then
checks:

  1. Data sanity: `base_r2` really is close to 0 (the weak baseline should
     not accidentally be predictive). If this fails, the fixture or the
     dataset changed underneath the task, not the learner's code.
  2. `eng_r2 - base_r2 >= GAIN` -- the engineered features must beat the
     weak baseline by a wide, unmistakable margin.
  3. `eng_r2 >= MIN_R2` -- the engineered features must reach a solid
     absolute R^2 on their own, not just "less bad than the baseline."

Run from the module root:

    uv run python 11-feature-engineering/tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, load_observations, not_passed, passed  # noqa: E402
from src.baseline import baseline_features, evaluate  # noqa: E402
from src.features import engineered_features  # noqa: E402

# Measured while authoring this task (full SCALE=1.0 data, Ridge(alpha=1.0)
# on the fixed split): base_r2 ~ -0.0002 (baseline.py's weak columns are
# genuinely close to independent of price), a category+site one-hot alone
# reaches ~0.44, and adding calendar + title features on top lands in the
# same ~0.43-0.44 neighborhood (calendar/title add little ON TOP of
# category, but are still worth having per the README). Thresholds below
# sit with real headroom under that ceiling so a reasonable-but-imperfect
# feature set (e.g. category one-hot without site or calendar) still
# passes, while a baseline-only or leakage-free-but-uninformative attempt
# (e.g. an ordinal category code instead of one-hot) does not.
MAX_SANE_BASE_R2 = 0.05   # data sanity gate on the fixture, not the learner
GAIN = 0.15                # eng_r2 - base_r2 must be at least this much
MIN_R2 = 0.25               # eng_r2 must reach at least this much on its own


@guarded
def main():
    df = load_observations()

    base_r2 = evaluate(baseline_features(df), df)

    if base_r2 > MAX_SANE_BASE_R2:
        not_passed(
            f"data sanity check failed: baseline_features scores R^2={base_r2:.4f}, "
            f"above the expected near-zero ceiling of {MAX_SANE_BASE_R2} -- the weak "
            f"baseline fixture or the dataset changed; this is not a learner error"
        )

    eng_features = engineered_features(df)
    eng_r2 = evaluate(eng_features, df)

    gain = eng_r2 - base_r2

    if gain < GAIN:
        not_passed(
            f"engineered_features only gained {gain:.4f} R^2 over the baseline "
            f"(base_r2={base_r2:.4f}, eng_r2={eng_r2:.4f}), need >= {GAIN} -- "
            f"the raw columns that actually carry price signal (category especially, "
            f"also title) don't look like they're in the feature matrix yet"
        )

    if eng_r2 < MIN_R2:
        not_passed(
            f"engineered_features reached R^2={eng_r2:.4f}, need >= {MIN_R2} -- "
            f"even accounting for the gain over baseline, this is too low; check that "
            f"category is one-hot encoded (not an ordinal code) and that the feature "
            f"matrix is really row-aligned with df"
        )

    passed(f"base_r2={base_r2:.4f}, eng_r2={eng_r2:.4f}, gain={gain:.4f}")


if __name__ == "__main__":
    main()
