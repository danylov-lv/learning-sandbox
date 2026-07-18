The pretend samples come from your own sample: resample it WITH
replacement, drawing the same number of points `n` as your original
sample has. Because it's with replacement, some points get picked more
than once in a given resample and others get skipped entirely -- that's
exactly what makes each resample different from the last, and different
from the original.

Do that many times (this task pins the count at `N_RESAMPLES = 2000`).
Each time, recompute your statistic (the median) on the resample, not on
the original sample. You end up with `N_RESAMPLES` recomputed medians --
that collection IS your approximation of the median's sampling
distribution. Its spread is your uncertainty.

The confidence interval itself is then almost embarrassingly simple once
you have that collection: it's just two percentiles of it. A 95% interval
is the 2.5th and 97.5th percentiles of your `N_RESAMPLES` recomputed
medians -- no separate formula, no distributional assumption, just
"sort them (conceptually) and read off where the middle 95% starts and
ends."

Two functions fall out of this naturally: one that produces the
collection of recomputed statistics, and one that reduces a collection
like that to a `(low, high)` pair of percentiles. The third function is
just "do both, in order."
