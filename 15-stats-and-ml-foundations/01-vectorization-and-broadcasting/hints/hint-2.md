Three different mechanisms for the three functions:

**`zscore_within_category`** -- you need a per-group mean and a per-group
std, then to subtract/divide each row by its OWN group's values. Grouped
sums keyed by small-integer codes are exactly what `np.bincount` computes
in one whole-array pass: `np.bincount(codes)` gives you a per-code count,
and `np.bincount(codes, weights=some_array)` gives you a per-code sum of
`some_array`. Once you have per-group sums and counts, you have per-group
means -- ordinary array division, no loop. The std needs a second pass
(you need the means before you can compute deviations from them), but it's
the same `bincount(weights=...)` trick applied to the squared deviations.
The "look this up for every row" step is fancy indexing: if `means` is a
length-K array (K = number of distinct groups), `means[codes]` is a
length-n array where each row already has ITS group's mean, ready to
subtract from `prices` directly.

**`rolling_mean`** -- the naive version re-sums the whole window at every
row, which is why it's O(n * window). You don't need to re-sum anything if
you keep a running total: `np.cumsum` gives you, at every index, the sum
of everything up to and including that index. The sum of any contiguous
slice `values[a:b]` is then just `cumsum[b-1] - cumsum[a-1]` (with the
usual off-by-one care at the array's start) -- one subtraction instead of
re-adding `window` numbers. Building the two arrays of window-start and
window-end indices for every row, and taking their difference, is itself a
whole-array operation (no per-row loop needed to build those index
arrays).

**`minmax_scale_per_group`** -- numpy doesn't have a single built-in as
convenient as `bincount` for a *grouped* min or max. The intended move here
is a loop, but over the DISTINCT group codes (there are only a handful of
categories), not over rows: for each group code, build a boolean mask
(`codes == g`), slice out just that group's values with the mask, and call
plain `.min()` / `.max()` on the slice -- each of those calls is itself a
whole-array numpy reduction, just scoped to one group at a time. A handful
of iterations, each one doing real vectorized work, is a completely
different cost profile than tens of thousands of row-by-row iterations.
