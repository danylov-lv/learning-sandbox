# Hint 2

For the scheduling section: a plain FIFO queue across all clients means
whichever tier fills the queue fastest (by raw record volume, not by
contractual importance) sets everyone else's latency. You need a policy
that is tier-aware without letting the lowest tier starve completely
forever — look into weighted fair queuing and strict-priority-with-a-floor
as two different answers to the same tradeoff, and pick one you can defend
under hostile questioning about who loses first.

For the capacity model: read the README's "Capacity model contract"
section fully before opening `src/estimate.py`. Every quantity has exactly
one pinned definition — which rate is "average" vs "peak," what a 30-day
month means for an error budget, and what "still serving live traffic"
means for the drain calculation. Don't derive your own reasonable-sounding
version of any of these; the validator recomputes the README's exact
formula independently and will not agree with a plausible-but-different
one.

For breach detection: a breach discovered when you generate the monthly
invoice is a breach discovered too late to fix and too late to dispute
credibly. Think about what has to be measured continuously versus what
can be reconciled in a monthly batch job.
