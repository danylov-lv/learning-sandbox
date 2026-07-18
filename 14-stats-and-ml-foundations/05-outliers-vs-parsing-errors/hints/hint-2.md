The key move: a missing-decimal price isn't just "big" -- it's a real,
ordinary price with two zeros' worth of magnitude bolted on. That means
there's a specific, testable transformation that undoes it: divide by 100.

Do that, per candidate row, and ask "does this now look like a normal price
for this row's category?" A genuine outlier fails this test in a
particular way: it's also large, but it's large because the *actual*
product is expensive -- dividing IT by 100 does not land you back in the
middle of the category's normal range, it lands you somewhere absurdly
cheap (a "real" flagship electronics item divided by 100 becomes an
implausible $15 gadget). A missing-decimal defect, by contrast, rejoins the
pack almost exactly, because that's what it always was before the decimal
point vanished.

"Does this look like a normal price for the category" needs a robust
center and a robust spread to compare against -- not the raw mean/std of
the category's prices (contaminated by the very outliers and defects
you're trying to separate), and not on the raw price scale (multiplicative
effects like "x100" are additive shifts on a *log* scale, which is exactly
why comparing distances in log-space is the natural fit here). The median
of `log(price)` per category, and the median absolute deviation from that
median, give you a center and scale that a handful of extreme values barely
move.

One more free signal, once you're looking at flagged rows up close: real
prices, drawn from a continuous distribution and typically stored to the
cent, almost always have a fractional part. A price that comes out an
exact, round, whole-dollar number, sitting well above where this category
normally lands, is a second independent tell pointing at the same
conclusion as the divide-by-100 test -- worth combining with it rather than
relying on either alone.
