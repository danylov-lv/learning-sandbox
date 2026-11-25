A concrete method, in prose (no ready-made code -- translate this into your
own pandas/numpy):

1. **Impossible values.** Any row with `price <= 0` or `price` is `NaN` ->
   parsing error. Done, no further test needed for these rows.

2. **Per-category robust reference.** For each `category`, using only the
   rows that survive step 1 (impossible values excluded), compute:
   - `center` = the median of `log(price)` for that category.
   - `scale` = the median absolute deviation of `log(price)` from `center`
     for that category, scaled by ~1.4826 so it estimates a standard
     deviation the way it would for a normal distribution (this is the
     standard MAD-to-sigma conversion factor -- look up why 1.4826
     specifically if you want the derivation).
   You now have one `(center, scale)` pair per category. This computation
   is contaminated by a small fraction of missing-decimal values and
   genuine outliers still sitting in the data, but the median and MAD are
   *robust statistics* specifically because a small contaminating fraction
   barely moves them -- that robustness is the whole reason to use them
   instead of mean/std here.

3. **Missing-decimal signature test**, for every row that survived step 1:
   - Compute `candidate = price / 100`.
   - Compute how many `scale`-units `log(candidate)` sits from that row's
     category `center` (an absolute z-score on the log scale, against the
     robust reference from step 2, not against the raw mean/std).
   - If that distance is small -- the candidate rejoins the pack -- AND the
     original `price` is a suspiciously round, whole-dollar figure (no
     fractional cents) that itself sits well above where the category
     normally lands, treat the row as a `missing_decimal` parsing error.
   - Tune "small" and "well above" empirically: print out how many rows
     get flagged, and at what distance the genuine-large-but-real prices
     start looking close to the boundary. You're looking for a threshold
     that clearly separates two populations, not one that happens to hit a
     round number.

4. **Everything else** -- any row not caught by steps 1 or 3 -- goes in
   `kept_ids`, genuine outliers included, no matter how large `price` is.

Before trusting your thresholds, spot-check by hand: pull out a handful of
rows your rule flags and a handful it doesn't, for the categories with the
widest price spread (electronics is the hardest case in this dataset --
its category has the widest normal price range, which is exactly what
makes separating "a real expensive gadget" from "a x100 typo" hardest
there). If your rule is flagging things that still look like plausible
real prices for that category, tighten the distance threshold; if it's
letting through values that are obviously ~100x a round number, loosen it.
