# 01 -- Vectorization and Broadcasting

## Backstory

A colleague needed a handful of derived metrics over the scraped product
data -- a within-category z-score for each price, a trailing rolling mean,
a per-category min-max scale -- and wrote them the way most people first
reach for: a `for` loop over the rows, one Python statement per
observation. It works. On the sample they tested with (a few hundred rows)
it even felt instant. Pointed at the real dataset (tens of thousands of
rows, and growing every scrape), it's now the slowest step in the pipeline,
and it's about to get slower, because nothing about a Python `for` loop
gets cheaper as the data grows -- it just does more of the same expensive
thing more times.

This is the same lesson module 05 taught with a Spark `pandas_udf` versus a
row-at-a-time Python UDF: pushing computation into a vectorized, whole-array
operation (there, Arrow-batched pandas; here, numpy broadcasting) lets the
heavy lifting happen in a single C-level loop instead of bouncing back into
the Python interpreter once per row. The mechanism is different -- numpy
here, not Spark -- but the shape of the win, and the reason a naive
row-by-row loop can't match it, is the same.

## What's given

- `src/naive.py` -- **fully implemented, not a stub.** Pure-Python,
  row-by-row reference implementations of three functions:
  `zscore_within_category(prices, category_codes)`,
  `rolling_mean(values, window)`, and
  `minmax_scale_per_group(values, group_codes)`. Read its docstrings
  carefully -- they spell out the exact semantics (how grouping works, how
  the rolling window behaves at the start of the array, how a constant
  group is handled) that your vectorized version must match. Don't edit
  this file; it's both your correctness reference and the thing you're
  trying to beat.
- `src/vectorized.py` -- the scaffold you implement, same three function
  signatures.
- `baseline.py` -- run this (not the validator) once `vectorized.py` is
  implemented. It builds a fixed input from the real shared dataset,
  checks your vectorized output against `naive.py`'s as a precondition,
  times both versions of all three functions on this machine, and writes
  `baseline-local.json` (gitignored).
- The shared dataset (`data/observations.parquet`, via
  `harness.common.load_observations()`) -- already generated at the module
  root.

## What's required

Implement all three functions in `src/vectorized.py` so that:

1. Each one produces output matching its `naive.py` counterpart within
   floating-point tolerance, for any valid input -- not just the specific
   input `baseline.py` happens to construct.
2. None of them contains a Python-level loop over the n rows. A small loop
   over the handful of *distinct* group codes is fine (there are only a
   few categories in this dataset); a loop that runs once per element of
   `prices`/`values` -- spelled as `for`, a list comprehension over
   indices, `.apply()` with a Python callable, or anything else that
   revisits the Python interpreter once per row -- defeats the point.

Think in terms of whole-array operations: grouped sums via `np.bincount`,
grouped extremes via a per-group boolean mask, cumulative sums for a
running window. The hints go deeper if you get stuck.

## Completion criteria

From this task's directory:

```bash
uv run python baseline.py
uv run python tests/validate.py
```

`tests/validate.py`:

- Recomputes the same fixed input independently (not by reading
  `baseline.py`'s output) and checks your `vectorized.py` functions match
  `naive.py`'s within tolerance.
- Reads `baseline-local.json` (`NOT PASSED`, telling you to run
  `baseline.py` first, if it's missing) and checks each function's
  vectorized-vs-naive speedup on your machine clears a threshold -- always
  relative to your own naive run, never an absolute wall-clock number.
- Prints `PASSED` with the three measured speedups, or
  `NOT PASSED: <reason>` and exits 1 -- including when `vectorized.py` is
  still unimplemented (`NotImplementedError` surfaces as a clean message,
  no traceback).

## Estimated evenings

1

## Topics to read up on

- numpy broadcasting rules -- how operations on arrays of different shapes
  implicitly align without an explicit loop
- Vectorization vs. Python-level loops -- why a numpy ufunc call is a
  single C loop, while a Python `for` loop over array elements pays full
  bytecode-interpretation overhead per element
- `np.bincount` (with and without `weights=`) for grouped sums/counts keyed
  by small-integer codes, and fancy indexing (`arr[codes]`) to broadcast a
  per-group result back to row shape
- `np.cumsum` and how a running total turns a sliding-window sum into an
  O(1)-per-row difference of two cumulative values, instead of re-summing
  the window every time
- Why C-level loops inside numpy release the GIL for their duration (same
  mechanism module 05's `pandas_udf` and module 11's GIL task both lean
  on), while a pure-Python loop never does -- vectorizing isn't just about
  raw speed, it's also what makes the work parallelizable later

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract
and dataset internals -- spoilers. Don't read it before finishing this
task.
