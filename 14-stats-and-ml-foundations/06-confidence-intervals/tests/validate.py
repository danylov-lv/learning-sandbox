"""Validator for 14-stats-and-ml-foundations task 06 -- confidence-intervals.

Everything here is graded against a reference this file computes itself
via scipy -- never against the learner's own `mean_confidence_interval`,
so a subtly-wrong formula can't accidentally "check itself" as correct.

Checks, in order:

1. `load_population()` (given, unmodified) returns a large-enough array.
2. `mean_confidence_interval(sample, 0.95)` on the FIXED sample
   (`SAMPLE_SEED`, `SAMPLE_SIZE`, drawn here exactly the way the task
   README documents) matches a scipy-computed reference interval within a
   tight float tolerance.
3. The pinned sample's CI actually contains the true population mean --
   verified once at authoring time to hold for this seed (see
   `.authoring/design.md`); this is a deterministic fact about a fixed
   sample and a correct formula, not a flaky probabilistic check.
4. The same function on a SMALL sample (n=15, a second fixed draw) is
   checked against its own scipy reference -- at small n the Student t
   critical value and the normal (z) critical value diverge by roughly
   9%, which is large next to the tolerance used here, so this step
   specifically catches "used 1.96 instead of scipy.stats.t.ppf(df=n-1)".
5. `ci_width_vs_sample_size(...)` is checked two ways: each returned
   width is compared against an independently-recomputed reference
   (same Monte Carlo recipe, computed here without calling the learner's
   `mean_confidence_interval`), and the returned widths themselves are
   checked for monotonic decrease and a width(50)/width(200) ratio near
   the theoretical `sqrt(200/50) = 2.0`.
6. `make_figure(population)` passes the structural `require_figure` check.

Run from this task's directory:

    uv run python tests/validate.py
"""

import sys
from pathlib import Path

import numpy as np
from scipy import stats

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import check_close, guarded, not_passed, passed, require_figure  # noqa: E402
from src.ci import (  # noqa: E402
    SAMPLE_SEED,
    SAMPLE_SIZE,
    WIDTH_REPEATS,
    WIDTH_SIZES,
    ci_width_vs_sample_size,
    load_population,
    make_figure,
    mean_confidence_interval,
)

# Second, independent fixed draw used only to stress small-n behavior
# (t vs z diverge most here). Not part of the task's documented "the"
# sample -- just an extra grading probe on the same generic function.
SMALL_SAMPLE_SEED = SAMPLE_SEED + 1
SMALL_SAMPLE_SIZE = 15

CI_TOL = dict(rel=1e-4, abs_=1e-6)
WIDTH_TOL = dict(rel=0.02, abs_=0.3)
RATIO_50_200_RANGE = (1.4, 2.8)  # sqrt(200/50) = 2.0, generous margin around it


def draw(population, size, seed):
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(population), size=size, replace=False)
    return population[idx]


def reference_ci(sample, confidence):
    n = len(sample)
    mean = float(np.mean(sample))
    sem = float(stats.sem(sample))
    q = 1 - (1 - confidence) / 2
    tcrit = float(stats.t.ppf(q, df=n - 1))
    half = tcrit * sem
    return mean - half, mean + half


def reference_width_vs_n(population, sizes, confidence, seed, repeats):
    rng = np.random.default_rng(seed)
    out = {}
    for n in sizes:
        widths = []
        for _ in range(repeats):
            idx = rng.choice(len(population), size=n, replace=False)
            low, high = reference_ci(population[idx], confidence)
            widths.append(high - low)
        out[n] = float(np.mean(widths))
    return out


def check_interval(label, got, ref_low, ref_high, hint=""):
    if not (isinstance(got, tuple) and len(got) == 2):
        not_passed(f"{label}: mean_confidence_interval must return a (low, high) tuple, got {got!r}")
    got_low, got_high = float(got[0]), float(got[1])
    if not (got_low < got_high):
        not_passed(f"{label}: CI bounds out of order: low={got_low} >= high={got_high}")

    ok, msg = check_close(f"{label} low", got_low, ref_low, **CI_TOL)
    if not ok:
        not_passed(msg + (f" -- {hint}" if hint else ""))
    ok, msg = check_close(f"{label} high", got_high, ref_high, **CI_TOL)
    if not ok:
        not_passed(msg + (f" -- {hint}" if hint else ""))
    return got_low, got_high


@guarded
def main():
    population = load_population()
    if len(population) < max(WIDTH_SIZES):
        not_passed(
            f"load_population() returned only {len(population)} rows, need at least "
            f"{max(WIDTH_SIZES)} -- did you modify load_population or the dataset?"
        )

    # --- 1. primary fixed sample (n=200) ---------------------------------
    sample = draw(population, SAMPLE_SIZE, SAMPLE_SEED)
    ref_low, ref_high = reference_ci(sample, 0.95)
    got = mean_confidence_interval(sample, 0.95)
    got_low, got_high = check_interval(f"CI (n={SAMPLE_SIZE})", got, ref_low, ref_high)

    pop_mean = float(population.mean())
    if not (got_low <= pop_mean <= got_high):
        not_passed(
            f"the fixed sample's 95% CI [{got_low:.2f}, {got_high:.2f}] does not contain "
            f"the true population mean ({pop_mean:.2f}) -- for this pinned seed a correctly "
            f"computed 95% CI should"
        )

    # --- 2. small-n sample (n=15) -- catches t-vs-z mistakes -------------
    small_sample = draw(population, SMALL_SAMPLE_SIZE, SMALL_SAMPLE_SEED)
    small_ref_low, small_ref_high = reference_ci(small_sample, 0.95)
    small_got = mean_confidence_interval(small_sample, 0.95)
    check_interval(
        f"CI (n={SMALL_SAMPLE_SIZE})",
        small_got,
        small_ref_low,
        small_ref_high,
        hint="check you're using scipy.stats.t.ppf(df=n-1), not a fixed z=1.96",
    )

    # --- 3. CI width vs sample size ---------------------------------------
    ref_widths = reference_width_vs_n(population, WIDTH_SIZES, 0.95, SAMPLE_SEED, WIDTH_REPEATS)
    got_widths = ci_width_vs_sample_size(population, WIDTH_SIZES, 0.95, SAMPLE_SEED, WIDTH_REPEATS)

    if not isinstance(got_widths, dict):
        not_passed(f"ci_width_vs_sample_size must return a dict, got {type(got_widths).__name__}")
    missing = [n for n in WIDTH_SIZES if n not in got_widths]
    if missing:
        not_passed(f"ci_width_vs_sample_size result missing size(s): {missing}")

    for n in WIDTH_SIZES:
        ok, msg = check_close(f"width(n={n})", float(got_widths[n]), ref_widths[n], **WIDTH_TOL)
        if not ok:
            not_passed(msg)

    widths_in_order = [float(got_widths[n]) for n in WIDTH_SIZES]
    if not all(widths_in_order[i] > widths_in_order[i + 1] for i in range(len(widths_in_order) - 1)):
        not_passed(
            f"CI widths are not monotonically decreasing across sizes {WIDTH_SIZES}: "
            f"{widths_in_order}"
        )

    ratio_50_200 = got_widths[WIDTH_SIZES[0]] / got_widths[WIDTH_SIZES[2]]
    lo, hi = RATIO_50_200_RANGE
    if not (lo <= ratio_50_200 <= hi):
        not_passed(
            f"width({WIDTH_SIZES[0]})/width({WIDTH_SIZES[2]}) = {ratio_50_200:.2f}, expected "
            f"roughly sqrt({WIDTH_SIZES[2]}/{WIDTH_SIZES[0]}) = "
            f"{(WIDTH_SIZES[2] / WIDTH_SIZES[0]) ** 0.5:.2f} (within [{lo}, {hi}]) -- "
            f"the 1/sqrt(n) shrink isn't showing up"
        )

    # --- 4. figure ---------------------------------------------------------
    fig = make_figure(population)
    ok, msg = require_figure(fig, min_axes=1)
    if not ok:
        not_passed(msg)

    passed(
        f"CI(n={SAMPLE_SIZE})=({got_low:.2f}, {got_high:.2f}), pop mean={pop_mean:.2f}; "
        f"width({WIDTH_SIZES[0]})/width({WIDTH_SIZES[2]})={ratio_50_200:.2f}"
    )


if __name__ == "__main__":
    main()
