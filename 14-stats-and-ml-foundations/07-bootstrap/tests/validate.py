"""Validator for 14-stats-and-ml-foundations task 07 -- bootstrap.

Independently reproduces the pinned resampling recipe (see the module
docstring in `src/bootstrap.py`) using only numpy and
`harness.common.load_observations()` -- never by calling into the
learner's own functions for the reference values. The learner's four
functions are then graded against that independent reference:

1. `bootstrap_distribution(sample, STATISTIC, N_RESAMPLES, BOOTSTRAP_SEED)`
   must reproduce the reference bootstrap array closely (the recipe is
   pinned exactly, so a correct implementation should match to a tight
   tolerance) and have length `N_RESAMPLES`.
2. `percentile_ci(ref_boot_stats, CONFIDENCE)` must reproduce the
   reference (low, high) percentiles.
3. `bootstrap_ci(sample, STATISTIC, ...)` -- the convenience wrapper --
   graded against the reference CI with a modest relative tolerance
   (`CI_REL_TOL = 1e-3`): loose enough to not be flaky if a correct-but-
   differently-ordered implementation picks up tiny float differences,
   tight enough that only a recipe that actually follows the pinned steps
   passes. This is the headline number `PASSED` reports.
4. The CI must be a proper interval bracketing both the sample's own point
   estimate and the TRUE population median (computed directly over the
   full valid-price population, independent of any sampling).
5. `require_figure` on the learner's `make_figure(...)` output.

Run from the module directory:

    uv run python 07-bootstrap/tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, load_observations, not_passed, passed, require_figure  # noqa: E402
from src.bootstrap import (  # noqa: E402
    BOOTSTRAP_SEED,
    CONFIDENCE,
    N_RESAMPLES,
    SAMPLE_SEED,
    SAMPLE_SIZE,
    STATISTIC,
    bootstrap_ci,
    bootstrap_distribution,
    make_figure,
    percentile_ci,
)

# CI bounds have genuine sampling variance baked in by design (that's the
# whole point of a bootstrap) -- but the recipe is pinned exactly (same
# seeds, same draw order), so a correct implementation should land very
# close to the independently-recomputed reference. 1e-3 relative tolerance
# is loose enough to absorb float-ordering noise, tight enough to reject a
# recipe that drifted (wrong replacement mode, re-seeded rng, wrong
# percentile bounds).
CI_REL_TOL = 1e-3
CI_ABS_TOL = 1e-6

# bootstrap_distribution should reproduce the reference array closely --
# same rng, same draw order, same statistic. A tighter tolerance than the
# CI check above is appropriate here since there's no aggregation smoothing
# out small per-element differences the way percentiles do.
ARRAY_REL_TOL = 1e-6
ARRAY_ABS_TOL = 1e-6

MIN_BOOT_STD = 0.5
MAX_BOOT_STD = 25.0


def _valid_usd_prices(df):
    """Same mechanical filter documented in src/bootstrap.py's
    load_valid_usd_prices -- reimplemented here independently so this
    validator never depends on learner-editable code for its reference
    values."""
    valid = df[(df["currency"] == "USD") & df["price"].notna() & (df["price"] > 0)]
    return valid["price"].to_numpy()


def _reference_sample(prices):
    import numpy as np

    rng = np.random.default_rng(SAMPLE_SEED)
    idx = rng.choice(len(prices), size=SAMPLE_SIZE, replace=False)
    return prices[idx]


def _reference_bootstrap(sample):
    import numpy as np

    n = len(sample)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    boot_stats = np.empty(N_RESAMPLES)
    for r in range(N_RESAMPLES):
        idx = rng.integers(0, n, size=n)
        boot_stats[r] = np.median(sample[idx])

    alpha = 1 - CONFIDENCE
    lo = float(np.percentile(boot_stats, 100 * alpha / 2))
    hi = float(np.percentile(boot_stats, 100 * (1 - alpha / 2)))
    return boot_stats, (lo, hi)


@guarded
def main():
    import numpy as np

    df = load_observations()
    prices = _valid_usd_prices(df)
    if len(prices) < SAMPLE_SIZE:
        not_passed(f"only {len(prices)} valid USD prices in the dataset, need >= {SAMPLE_SIZE}")

    population_median = float(np.median(prices))

    sample = _reference_sample(prices)
    point_estimate = float(np.median(sample))
    ref_boot_stats, (ref_lo, ref_hi) = _reference_bootstrap(sample)

    # 1. bootstrap_distribution
    got_boot = np.asarray(bootstrap_distribution(sample, STATISTIC, N_RESAMPLES, BOOTSTRAP_SEED), dtype=float)
    if got_boot.shape != (N_RESAMPLES,):
        not_passed(f"bootstrap_distribution returned shape {got_boot.shape}, want ({N_RESAMPLES},)")

    if not np.allclose(got_boot, ref_boot_stats, rtol=ARRAY_REL_TOL, atol=ARRAY_ABS_TOL):
        max_diff = float(np.max(np.abs(got_boot - ref_boot_stats)))
        not_passed(
            f"bootstrap_distribution diverges from the pinned recipe (max abs diff "
            f"{max_diff:.6f} across {N_RESAMPLES} resamples) -- check: one rng created "
            f"before the loop (not re-seeded per iteration), idx = rng.integers(0, n, "
            f"size=n) WITH replacement each iteration, statistic applied to sample[idx]"
        )

    boot_std = float(np.std(got_boot))
    if not (MIN_BOOT_STD <= boot_std <= MAX_BOOT_STD):
        not_passed(
            f"bootstrap_distribution spread (std={boot_std:.4f}) is outside the expected "
            f"range [{MIN_BOOT_STD}, {MAX_BOOT_STD}] -- looks collapsed (near-zero, maybe "
            f"every resample is identical) or blown up (maybe not resampling per iteration)"
        )

    # 2. percentile_ci, tested against the reference bootstrap array directly
    # (isolated from any bootstrap_distribution discrepancy above)
    got_lo, got_hi = percentile_ci(ref_boot_stats, CONFIDENCE)
    if not (np.isclose(got_lo, ref_lo, rtol=CI_REL_TOL, atol=CI_ABS_TOL) and np.isclose(got_hi, ref_hi, rtol=CI_REL_TOL, atol=CI_ABS_TOL)):
        not_passed(
            f"percentile_ci({{{N_RESAMPLES} boot stats}}, {CONFIDENCE}) returned "
            f"({got_lo!r}, {got_hi!r}), want approximately ({ref_lo!r}, {ref_hi!r}) -- "
            f"check the percentile bounds are 100*alpha/2 and 100*(1-alpha/2) with "
            f"alpha = 1 - confidence, via np.percentile's default interpolation"
        )

    # 3. bootstrap_ci -- the headline convenience function
    ci_lo, ci_hi = bootstrap_ci(sample, STATISTIC, N_RESAMPLES, CONFIDENCE, BOOTSTRAP_SEED)
    if not (np.isclose(ci_lo, ref_lo, rtol=CI_REL_TOL, atol=CI_ABS_TOL) and np.isclose(ci_hi, ref_hi, rtol=CI_REL_TOL, atol=CI_ABS_TOL)):
        not_passed(
            f"bootstrap_ci returned ({ci_lo!r}, {ci_hi!r}), want approximately "
            f"({ref_lo!r}, {ref_hi!r}) (rel tol {CI_REL_TOL}) -- this should be equivalent "
            f"to percentile_ci(bootstrap_distribution(...)) on the exact pinned recipe"
        )

    # 4. proper interval: low < point estimate < high
    if not (ci_lo < point_estimate < ci_hi):
        not_passed(
            f"bootstrap_ci=({ci_lo:.4f}, {ci_hi:.4f}) does not bracket the sample's own "
            f"point estimate ({point_estimate:.4f}) -- a valid CI must contain the "
            f"statistic it was built around"
        )

    # 5. brackets the TRUE population median (computed over the whole valid
    # population, independent of the sample/bootstrap machinery entirely)
    if not (ci_lo < population_median < ci_hi):
        not_passed(
            f"bootstrap_ci=({ci_lo:.4f}, {ci_hi:.4f}) does not bracket the true population "
            f"median ({population_median:.4f}) computed over all {len(prices)} valid USD "
            f"prices -- with the pinned seeds this should hold; if it doesn't, something in "
            f"the recipe (sample draw, resampling, or percentile bounds) has drifted"
        )

    # 6. figure
    fig = make_figure(got_boot, (ci_lo, ci_hi))
    ok, msg = require_figure(fig)
    if not ok:
        not_passed(f"make_figure: {msg}")

    passed(
        f"median bootstrap 95% CI = ({ci_lo:.2f}, {ci_hi:.2f}), point estimate = "
        f"{point_estimate:.2f}, population median = {population_median:.2f}, "
        f"boot_std = {boot_std:.3f}"
    )


if __name__ == "__main__":
    main()
