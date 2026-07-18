A mean computed from a sample is not "the" answer -- it's one draw from a
distribution of possible answers. Scrape a different 200 pages from the
same population and you'd get a different average. That average-of-
averages distribution has its own spread, smaller than the spread of the
raw prices themselves but not zero. The standard error of the mean is what
measures that spread. A confidence interval turns "the standard error" into
a range you can hand to someone who doesn't think in standard deviations:
"the true average is very likely in here."

Before writing any code, get clear on the difference between two numbers
that are easy to conflate: the standard deviation of the sample's raw
values (how spread out individual prices are), and the standard error of
the sample mean (how spread out the *average* would be if you kept
resampling). They're related by a factor that involves the sample size --
which is exactly why a bigger sample gives you a tighter interval even
though the underlying prices are just as spread out as ever.
