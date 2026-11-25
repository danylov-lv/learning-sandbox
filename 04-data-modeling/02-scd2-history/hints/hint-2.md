# Hint 2

Constructing the intervals: take the ordered sequence of "this entity's
attribute became X at time T" facts (the initial `shop_registered` /
`product_discovered` value counts as the first fact, at its `event_time`).
Each fact closes the previous interval and opens a new one — the new row's
`valid_from` is this fact's `event_time`, and the *previous* row's
`valid_to` becomes this fact's `event_time` too. The current, still-open
interval gets `valid_to = NULL` (or a sentinel far-future timestamp,
whichever you find easier to query against) since nothing has closed it yet.

Make the intervals half-open: `[valid_from, valid_to)`. That means "as of
time t" is simply `valid_from <= t AND (valid_to IS NULL OR t < valid_to)` —
no off-by-one arguing about whether the boundary instant belongs to the old
value or the new one, and adjacent intervals never gap or overlap if you
built them correctly.

For product brand/category specifically: remember the initial value comes
from the *first* `product_discovered` across all shops for that
`product_code`, not from every shop's discovery of it.
