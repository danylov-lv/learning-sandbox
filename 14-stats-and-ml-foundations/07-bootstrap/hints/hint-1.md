You need a confidence interval for a median. There's no formula for the
standard error of a median sitting in a textbook the way there is for a
mean -- the sampling distribution of a median depends on the shape of the
underlying data in a way that doesn't collapse to one plug-in number.

If you can't derive the sampling distribution of a statistic analytically,
you can still find out how much it varies: simulate it. You only have one
sample, but you can generate many "pretend samples" from it and watch how
the statistic moves across them. The spread of the statistic across those
pretend samples stands in for the spread you'd see if you'd actually drawn
many real samples from the population.

Where do the pretend samples come from, if you only have one real sample?
That's the part to think about before opening `src/bootstrap.py`.
