"""Validator for 14-stats-and-ml-foundations task 01 --
vectorization-and-broadcasting.

Two independent things must be true:

1. Correctness -- src/vectorized.py's three functions, called on the SAME
   fixed input baseline.py uses (rebuilt independently here via
   `baseline.build_input`, not read from a file), produce output matching
   src/naive.py's reference within floating-point tolerance (np.allclose).
2. Speed -- baseline-local.json (written by `uv run python baseline.py`,
   which itself requires vectorized.py to already be correct -- it checks
   this before timing anything) shows each vectorized function beats its
   naive counterpart by at least a threshold speedup. Every threshold is
   RELATIVE to your own machine's naive run, never an absolute wall-clock
   number, with margins set well below what was measured while authoring
   this task (see MIN_SPEEDUP below).

Run from this task's directory:

    uv run python baseline.py
    uv run python tests/validate.py
"""

import sys
from pathlib import Path

import numpy as np

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from baseline import build_input  # noqa: E402
from harness.common import guarded, not_passed, passed, read_baseline  # noqa: E402
from src.naive import ROLLING_WINDOW  # noqa: E402
from src.naive import minmax_scale_per_group as naive_minmax  # noqa: E402
from src.naive import rolling_mean as naive_rolling  # noqa: E402
from src.naive import zscore_within_category as naive_zscore  # noqa: E402
from src.vectorized import minmax_scale_per_group as vec_minmax  # noqa: E402
from src.vectorized import rolling_mean as vec_rolling  # noqa: E402
from src.vectorized import zscore_within_category as vec_zscore  # noqa: E402

BASELINE_PATH = "01-vectorization-and-broadcasting/baseline-local.json"

# Minimum required speedup (vectorized vs naive), set well below what was
# measured on the authoring machine across repeated runs (zscore ~63-128x,
# rolling_mean ~174-242x, minmax_scale_per_group ~23-28x) so this doesn't
# flake on a slower or busier machine, while still ruling out a "technically
# vectorized but still secretly O(n * window)" or similarly half-hearted
# implementation.
MIN_SPEEDUP = {
    "zscore_within_category": 15.0,
    "rolling_mean": 40.0,
    "minmax_scale_per_group": 8.0,
}


def check_correctness():
    prices, category_codes = build_input()

    checks = [
        ("zscore_within_category", naive_zscore(prices, category_codes), vec_zscore(prices, category_codes)),
        ("rolling_mean", naive_rolling(prices, ROLLING_WINDOW), vec_rolling(prices, ROLLING_WINDOW)),
        ("minmax_scale_per_group", naive_minmax(prices, category_codes), vec_minmax(prices, category_codes)),
    ]
    for name, naive_out, vec_out in checks:
        naive_out = np.asarray(naive_out, dtype=np.float64)
        vec_out = np.asarray(vec_out, dtype=np.float64)
        if vec_out.shape != naive_out.shape:
            not_passed(f"{name}: expected output shape {naive_out.shape}, got {vec_out.shape}")
        if not np.allclose(naive_out, vec_out):
            max_diff = float(np.max(np.abs(naive_out - vec_out)))
            not_passed(f"{name}: vectorized output does not match naive (max abs diff {max_diff:.6g})")


def check_speed():
    baseline = read_baseline(BASELINE_PATH)
    if baseline is None:
        not_passed(f"{BASELINE_PATH} not found -- run `uv run python baseline.py` first")

    speedups = {}
    for name, min_speedup in MIN_SPEEDUP.items():
        entry = baseline.get(name)
        if not entry or "naive_seconds" not in entry or "vectorized_seconds" not in entry:
            not_passed(f"baseline-local.json missing timing data for {name} -- rerun `uv run python baseline.py`")

        naive_seconds = entry["naive_seconds"]
        vectorized_seconds = entry["vectorized_seconds"]
        if not isinstance(naive_seconds, (int, float)) or naive_seconds <= 0:
            not_passed(f"baseline-local.json {name}.naive_seconds is not a positive number: {naive_seconds!r}")
        if not isinstance(vectorized_seconds, (int, float)) or vectorized_seconds <= 0:
            not_passed(f"baseline-local.json {name}.vectorized_seconds is not a positive number: {vectorized_seconds!r}")

        speedup = naive_seconds / vectorized_seconds
        speedups[name] = speedup
        if speedup < min_speedup:
            not_passed(
                f"{name}: vectorized speedup {speedup:.2f}x is below the required {min_speedup}x "
                f"(naive={naive_seconds:.4f}s, vectorized={vectorized_seconds:.6f}s) -- check for a "
                f"per-row Python loop hiding in src/vectorized.py"
            )
    return speedups


@guarded
def main():
    check_correctness()
    speedups = check_speed()

    passed("speedups: " + ", ".join(f"{name}={s:.1f}x" for name, s in speedups.items()))


if __name__ == "__main__":
    main()
