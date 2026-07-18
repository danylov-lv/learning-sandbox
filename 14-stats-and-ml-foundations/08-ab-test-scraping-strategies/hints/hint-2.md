The specific test here is the pooled two-proportion z-test. "Pooled"
matters: under the null hypothesis (A and B share one true success rate),
the best estimate of that shared rate uses BOTH samples combined -- not
`p_a`, not `p_b`, not their unweighted average, but the total number of
successes across both groups divided by the total number of attempts
across both groups. Everything downstream (the standard error, the
z-statistic) is built from that pooled estimate, not from `p_a` and `p_b`
separately.

Once you have a z-statistic, converting it to a p-value is a standard-normal
CDF lookup, and it needs to be TWO-sided: you care about a gap in either
direction (B could plausibly have come out worse, and the test shouldn't
assume you already know which way the difference would go). `scipy.stats`
has what you need for the CDF; you don't need `statsmodels`.

Keep effect size mentally separate from the p-value the whole time you're
building this. The p-value answers "how confident should I be that a
difference exists at all." Effect size (the raw gap, or the relative lift)
answers "how big is it, and is it big enough to matter for the decision at
hand" (here: is B's improvement worth its extra cost). A large sample can
make a tiny, practically irrelevant gap statistically significant --
significance is not the same claim as "this matters."

For the figure: a confidence interval on EACH proportion, separately, is
what makes "are these two groups actually different" visually legible
before anyone reads a p-value. Two non-overlapping error bars is a strong
visual signal; two heavily-overlapping ones is a visual hint toward "not
significant," even before the test runs. You don't need the pooled
standard error for this plot -- each group's own CI uses that group's own
proportion and sample size.
