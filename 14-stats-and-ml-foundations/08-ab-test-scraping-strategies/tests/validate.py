"""Validator for 14-stats-and-ml-foundations task 08 -- ab-test-scraping-strategies.

Independently recomputes the pooled two-proportion z-test (via scipy, not
your code) on the SAME fixture data your `two_proportion_test` sees, then
grades your implementation:

  1. `simulate_experiment()` (the fully-implemented fixture, unchanged) is
     called at its default seed -- 1500 attempts each for strategy A and B.
  2. The reference: pooled proportion, pooled standard error, z-statistic,
     and two-sided p-value, computed directly from `a`/`b` here, not from
     your code.
  3. Your `two_proportion_test(a, b)` is graded against that reference:
     p_a, p_b, diff, z, p_value, relative_lift, each within a float
     tolerance.
  4. Your `interpret(result, alpha=0.05)` must agree with the reference's
     own significance decision (at the default seed, the true gap is large
     enough relative to the sample size that this is comfortably the
     "significant" branch -- see the numbers this validator prints).
  5. `make_figure(a, b, result)` must return a matplotlib Figure with
     actual drawn content (`require_figure`).

Run from this task's directory:

    uv run python tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import check_close, guarded, not_passed, passed, require_figure  # noqa: E402
from src.experiment import simulate_experiment  # noqa: E402
from src.abtest import interpret, make_figure, two_proportion_test  # noqa: E402

ALPHA = 0.05

REQUIRED_TEST_KEYS = ["p_a", "p_b", "diff", "z", "p_value", "relative_lift"]
REQUIRED_INTERPRET_KEYS = ["significant", "reject_null", "verdict"]


def reference_two_proportion_test(a, b):
    """Pooled two-proportion z-test, computed independently of src/abtest.py."""
    import numpy as np
    from scipy.stats import norm

    n_a, n_b = len(a), len(b)
    x_a, x_b = int(a.sum()), int(b.sum())
    p_a, p_b = x_a / n_a, x_b / n_b
    diff = p_b - p_a

    p_pool = (x_a + x_b) / (n_a + n_b)
    se = (p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b)) ** 0.5
    z = diff / se
    p_value = 2 * (1 - norm.cdf(abs(z)))
    relative_lift = diff / p_a

    return {
        "p_a": p_a,
        "p_b": p_b,
        "diff": diff,
        "z": z,
        "p_value": p_value,
        "relative_lift": relative_lift,
    }


@guarded
def main():
    data = simulate_experiment()
    a, b = data["a"], data["b"]

    ref = reference_two_proportion_test(a, b)

    result = two_proportion_test(a, b)
    if not isinstance(result, dict):
        not_passed(f"two_proportion_test must return a dict, got {type(result).__name__}")

    missing = [k for k in REQUIRED_TEST_KEYS if k not in result]
    if missing:
        not_passed(f"two_proportion_test result missing key(s): {missing}")

    # p_value legitimately has more room: it's the most sensitive quantity
    # (exponentiated through the normal CDF), so a slightly different but
    # still-correct implementation detail can shift it more than a linear
    # quantity like p_a/diff would. Still tight enough to catch a wrong
    # formula (one-sided, chi-squared, unpooled SE, etc.).
    tolerances = {
        "p_a": dict(rel=1e-6, abs_=1e-9),
        "p_b": dict(rel=1e-6, abs_=1e-9),
        "diff": dict(rel=1e-6, abs_=1e-9),
        "z": dict(rel=1e-4, abs_=1e-6),
        "p_value": dict(rel=1e-2, abs_=1e-6),
        "relative_lift": dict(rel=1e-4, abs_=1e-6),
    }
    for key, tol in tolerances.items():
        ok, msg = check_close(key, float(result[key]), ref[key], **tol)
        if not ok:
            not_passed(f"two_proportion_test: {msg}")

    if ref["p_value"] >= ALPHA:
        # Should never happen at the pinned default seed -- guard against a
        # future accidental change to the fixture's seed/params silently
        # breaking the "exercise the significant branch" guarantee.
        not_passed(
            f"fixture's reference p_value ({ref['p_value']!r}) is not below "
            f"alpha={ALPHA} -- the default seed must produce a detectable "
            f"effect; this indicates src/experiment.py was modified"
        )

    verdict = interpret(result, alpha=ALPHA)
    if not isinstance(verdict, dict):
        not_passed(f"interpret must return a dict, got {type(verdict).__name__}")

    missing = [k for k in REQUIRED_INTERPRET_KEYS if k not in verdict]
    if missing:
        not_passed(f"interpret result missing key(s): {missing}")

    if bool(verdict["significant"]) is not True:
        not_passed(
            f"interpret(result, alpha={ALPHA})['significant'] = "
            f"{verdict['significant']!r}, expected True -- reference p_value "
            f"is {ref['p_value']!r}, well below alpha"
        )
    if bool(verdict["reject_null"]) is not True:
        not_passed(
            f"interpret(result, alpha={ALPHA})['reject_null'] = "
            f"{verdict['reject_null']!r}, expected True (should match "
            f"'significant')"
        )
    if not str(verdict.get("verdict", "")).strip():
        not_passed("interpret result's 'verdict' field is empty")

    fig = make_figure(a, b, result)
    ok, msg = require_figure(fig, min_axes=1)
    if not ok:
        not_passed(msg)

    passed(
        f"p_a={ref['p_a']:.4f}, p_b={ref['p_b']:.4f}, diff={ref['diff']:.4f}, "
        f"z={ref['z']:.3f}, p_value={ref['p_value']:.3e} -- significant at "
        f"alpha={ALPHA}"
    )


if __name__ == "__main__":
    main()
