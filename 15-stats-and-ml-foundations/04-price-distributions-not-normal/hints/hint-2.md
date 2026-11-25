Three separate questions, three separate numbers, in this order:

1. **How skewed is it?** A single number that's 0 for a symmetric
   distribution and positive when the tail stretches to the right. `scipy.
   stats` has a function that computes exactly this for a 1-D array.

2. **How heavy are the tails / how peaked is the middle, relative to a
   normal distribution?** A related but different single number, again 0
   for something normal-shaped. `scipy.stats` has a function for this too --
   check its default parameter for which convention it reports (there are
   two common conventions for this statistic; you want the one where a
   normal distribution scores 0, not 3).

3. **Is this consistent with having been drawn from a normal distribution
   at all?** This isn't a summary statistic, it's a hypothesis test --
   it returns a p-value. `scipy.stats` has a function for this named after
   the fact that it's literally testing for normality. Read what its null
   hypothesis is before you interpret the number it gives you.

Compute all three on the raw prices, then compute all three again on
`np.log(prices)`, and compare each pair. Do the numbers move in the
direction the histogram shapes from hint 1 predicted?

Once you've computed the raw-vs-log comparison, you need one boolean
judgment call: is the log-transformed distribution meaningfully "more
normal" than the raw one? Don't reach for an arbitrary threshold -- the
`log_makes_it_normal` docstring in `src/distributions.py` gives you the
exact rule to implement, including a specific worked-out reason why
comparing p-values directly doesn't work cleanly at this sample size. Read
it carefully before you write the boolean expression.
