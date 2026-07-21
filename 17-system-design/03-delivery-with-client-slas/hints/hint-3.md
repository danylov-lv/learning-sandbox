# Hint 3

For `src/estimate.py`, work through the dependency order by hand before
writing any function body — several of these functions are defined in
terms of earlier ones, and the README spells out exactly which:

1. Total daily volume is a sum over tiers of (client count x records per
   client per day). Everything else about rate flows from this one number
   and the length of a day in seconds.
2. Peak rate is the average rate scaled by a single workload-level factor
   — nothing more.
3. An error budget is "how much of the month can this tier be unavailable"
   — convert a percentage-point gap from 100% directly into minutes of a
   fixed-length month. Don't use a real calendar month; the README pins
   the exact number of minutes to use.
4. The backlog from an outage is just a rate held constant over a window
   — pick the one rate the README tells you to use (it is deliberately
   not the peak rate).
5. Draining that backlog while still serving live traffic means your
   drain capacity has to cover both the backlog and the ongoing arrivals
   at once — the "spare" rate available for backlog is capacity minus
   what's still arriving, not the full rated capacity.
6. The total recovery clock the freshness deadlines get compared against
   runs from the moment the outage starts, not from the moment it ends.

For the design doc's prioritization section, before writing prose, sketch
(on paper, not in the file) what happens to the queue depth for each tier
in a period where incoming volume exceeds the shared crawl budget — which
tier's queue grows unboundedly under your chosen policy, and at what point
(if any) you intervene.
