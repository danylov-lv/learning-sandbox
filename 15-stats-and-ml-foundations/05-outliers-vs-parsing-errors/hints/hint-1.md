Split the problem into two very different sub-problems, because they need
two very different tests.

The `negative`, `zero`, and `nan` cases are free -- there is no price in
the real world that is negative, exactly zero, or missing that isn't a
data-quality problem. No statistics required: a simple comparison catches
all three, with zero risk of ever catching a genuine outlier (a real
expensive product is never negative, zero, or missing).

The hard part -- the actual point of this task -- is `missing_decimal`
versus a genuine outlier. Both are large positive numbers. Both can be
*very* large. "How large is too large" is not a question with a single
global answer, because the two failure modes look identical from far away:
a $4,000 "price" could be a genuine flagship electronics item, or it could
be a $40 item with a dropped decimal point. You cannot tell which just by
looking at the raw magnitude.

Start by getting the free 75% (three of the four defect kinds) working and
correct, then spend your real effort on the missing-decimal-vs-genuine-
outlier problem. Don't reach for "3 standard deviations from the mean" as
your first move on the hard part -- try it if you want, but look closely at
what the mean and standard deviation of this column actually equal once a
few $170,000 missing-decimal values are sitting inside it, and ask whether
those two numbers still mean what you think they mean.
