"""Benchmark src/naive.py vs src/vectorized.py on THIS machine, over a
fixed, deterministic slice of the shared observations dataset, and write
the results to a gitignored `baseline-local.json` via
`harness.common.write_baseline`.

Run this AFTER implementing `src/vectorized.py`:

    uv run python baseline.py

Then verify with:

    uv run python tests/validate.py

Input construction (documented so the choice is not a mystery): rather than
synthesizing data, this uses the real shared dataset via
`load_observations()`, filtered down to finite, positive prices
(`np.isfinite(price) & (price > 0)`) -- a simple, deterministic filter, not
the module's full defect/validity logic (that's what task 05 is for; this
task only needs clean numeric input to time against, not a defect-free
sample). Category codes are integers `[0, 8)` from the fixed `CATEGORIES`
order in `generate.py`. Row order is whatever `load_observations()` returns
(the parquet file's on-disk order), which is fixed for a given
`data/observations.parquet` -- no shuffling, so this is reproducible run to
run on one machine.
"""

import sys
from pathlib import Path

import numpy as np

TASK_ROOT = Path(__file__).resolve().parent
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from generate import CATEGORIES  # noqa: E402
from harness.common import load_observations, time_it, write_baseline  # noqa: E402
from src.naive import ROLLING_WINDOW  # noqa: E402
from src.naive import minmax_scale_per_group as naive_minmax
from src.naive import rolling_mean as naive_rolling
from src.naive import zscore_within_category as naive_zscore
from src.vectorized import minmax_scale_per_group as vec_minmax  # noqa: E402
from src.vectorized import rolling_mean as vec_rolling
from src.vectorized import zscore_within_category as vec_zscore


def build_input():
    df = load_observations()
    price = df["price"].to_numpy()
    mask = np.isfinite(price) & (price > 0)

    prices = price[mask].astype(np.float64)

    cat_to_code = {c: i for i, c in enumerate(CATEGORIES)}
    categories = df.loc[mask, "category"].to_numpy()
    category_codes = np.array([cat_to_code[c] for c in categories], dtype=np.int64)

    return prices, category_codes


def main():
    prices, category_codes = build_input()
    print(f"input: {len(prices)} rows, {len(CATEGORIES)} categories, ROLLING_WINDOW={ROLLING_WINDOW}")

    # Precondition: vectorized must already agree with naive before timing
    # either -- a fast-but-wrong implementation is not a passing one.
    checks = [
        ("zscore_within_category", naive_zscore(prices, category_codes), vec_zscore(prices, category_codes)),
        ("rolling_mean", naive_rolling(prices, ROLLING_WINDOW), vec_rolling(prices, ROLLING_WINDOW)),
        ("minmax_scale_per_group", naive_minmax(prices, category_codes), vec_minmax(prices, category_codes)),
    ]
    for name, naive_out, vec_out in checks:
        if not np.allclose(naive_out, vec_out):
            max_diff = np.max(np.abs(np.asarray(naive_out) - np.asarray(vec_out)))
            print(f"MISMATCH in {name}: max abs diff = {max_diff}")
            sys.exit(1)
        print(f"correctness ok: {name} (vectorized matches naive, np.allclose)")

    result = {}

    for name, naive_fn, vec_fn, args in [
        ("zscore_within_category", naive_zscore, vec_zscore, (prices, category_codes)),
        ("rolling_mean", naive_rolling, vec_rolling, (prices, ROLLING_WINDOW)),
        ("minmax_scale_per_group", naive_minmax, vec_minmax, (prices, category_codes)),
    ]:
        _, naive_seconds = time_it(naive_fn, *args)
        _, vectorized_seconds = time_it(vec_fn, *args)
        speedup = naive_seconds / vectorized_seconds
        print(f"{name}: naive={naive_seconds:.4f}s vectorized={vectorized_seconds:.6f}s speedup={speedup:.1f}x")
        result[name] = {"naive_seconds": naive_seconds, "vectorized_seconds": vectorized_seconds}

    path = write_baseline("01-vectorization-and-broadcasting/baseline-local.json", result)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
