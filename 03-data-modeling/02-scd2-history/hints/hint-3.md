# Hint 3

Building intervals in one pass: pull the ordered change facts per entity
(one query per attribute-family is fine — shop name, shop tier, product
brand, product category can each be built the same way independently), then
use a window function partitioned by the entity key and ordered by
`event_time`. `LEAD(event_time) OVER (PARTITION BY entity_key ORDER BY
event_time)` gives you, for each row, the `event_time` of the *next* change
for that same entity — that's exactly your `valid_to` (NULL when there is no
next row, meaning still current). No self-join, no recursive CTE needed.

Joining an as-of question against this: for something like "the shop's tier
as of this observation's event_time," join the observation to the tier
history table on `shop_code` plus a range condition — the observation's
`event_time` falling inside `[valid_from, valid_to)`. A plain `BETWEEN`-style
predicate with the NULL-check for the open end works; if you want the
database to enforce that intervals for the same entity never overlap (an
integrity guarantee, not required for the questions but worth knowing
about), look at Postgres range types plus an `EXCLUDE` constraint via the
`btree_gist` extension.

For q05: compute the as-of tier per observation via this join, then
aggregate — don't try to precompute "average tier" per shop, since a shop
can appear under two different tiers within the same December if it changed
mid-month.
