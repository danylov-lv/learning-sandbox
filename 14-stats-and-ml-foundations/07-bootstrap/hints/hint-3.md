No ready-made code here -- this is the concrete shape of the recipe in
prose, close enough to pseudocode that translating it into `bootstrap.py`
should be mechanical.

**`bootstrap_distribution`**: allocate (or otherwise build) an output
container of length `n_resamples`. Before any looping, create exactly one
random generator from the given `seed` -- this matters for
reproducibility: if you create a new generator inside the loop, or reuse
`np.random` global state instead of an explicit generator, your sequence
of draws won't match anyone else's, including your own on a re-run. Then
loop `n_resamples` times; each iteration, draw `n = len(sample)` integer
indices in `[0, n)` FROM THAT SAME GENERATOR, allowing repeats (this is
"with replacement" -- look at what `Generator.integers` does when you ask
for `size=n` from a half-open range without telling it to avoid repeats).
Index into `sample` with those indices to build one resample, apply
`statistic_fn` to it, and store the result at the current position in
your output container. After the loop, you have `n_resamples` values --
return them as an array.

**`percentile_ci`**: given `confidence` (e.g. `0.95`), work out
`alpha = 1 - confidence` first. The two percentile ranks you need are
`100 * alpha / 2` (low) and `100 * (1 - alpha / 2)` (high) -- for
`confidence=0.95` these are `2.5` and `97.5`. Feed each rank to a
percentile function over your bootstrap array; return the two results as
a pair, low first.

**`bootstrap_ci`**: call the two functions above in sequence, passing
their outputs through -- there's no new logic here, just wiring. Resist
the temptation to write a second, slightly different resampling loop
inside this function; if you do, you now have two recipes that can drift
apart from each other.

**`make_figure`**: a histogram (`ax.hist(...)`) of the bootstrap array is
the main content. Add two vertical lines (`ax.axvline(...)`) at the CI
bounds you were given, and a third one somewhere near the middle of the
distribution for the point estimate -- since this function only receives
the bootstrap array and the CI, not the original sample, the middle of
the bootstrap distribution itself (its own median) is a reasonable stand-
in for "the point estimate" here. Give the three lines different colors
or line styles and a legend so a reader can tell which is which at a
glance.
