# Hint 1

Start from the two reads, not the schema. One read wants "everything about
one product, ordered by time, over a range" -- that's a locality problem:
rows for the same product should sit physically close together on disk so
a range scan doesn't have to hop around. The other read wants "everything
about one day (or category), across many products" -- a completely
different locality need. A single physical ordering can't be optimal for
both; figure out which one you're optimizing for and be honest in the
design doc about what it costs the other one.

Separately, think about what a "row" even is here. Every scrape observation
could become a row, or you could store only the ones where the price
changed and reconstruct the rest at read time. That's a real trade-off with
real numbers behind it -- don't resolve it by intuition alone, let the
capacity model's two variants (full vs change-only) inform the decision.

Also think about time before you think about disk cost: five years of
history doesn't need to be equally accessible on day one and on day 1,800.
What does "hot" mean for a charting query, and how far back does it
realistically need to reach fast?
