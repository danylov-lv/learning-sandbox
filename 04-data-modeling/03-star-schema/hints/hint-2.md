# Hint 2

Populate the dimensions first, straight out of your existing SCD2 tables
from task 02 — a `dim_shop` row per (shop, validity interval) and a
`dim_product` row per (product, validity interval), each getting its own
surrogate key. If your task-02 tables already carry `valid_from`/`valid_to`
per version, this is close to a direct copy with a generated key added; if
you collapsed some of that history, you may need to reconstruct the
intervals here instead.

For `dim_date`, generate one row per calendar day across the business
period with `generate_series(start, end, interval '1 day')`, then derive
whatever columns let q09/q11 group by month or quarter as a plain column
equality — no `date_trunc` or `EXTRACT` needed inside q09–q11 themselves.
A date dimension's job is to have already done that classification once.

The interesting part is the fact table population: for every deduplicated
observation, you need to find the one `dim_shop` row and the one
`dim_product` row whose validity interval contains that observation's
`event_time`. That's a join on the natural key (shop_code / product_code)
plus a half-open interval predicate (`valid_from <= event_time AND
(valid_to IS NULL OR event_time < valid_to)`), picked at population time,
its resulting surrogate key baked into the fact row. Do this once, in the
INSERT that builds the fact table — not as something q09–q11 have to
redo.

Deduplication and USD conversion belong in this same population step too:
by the time a row lands in the fact table, it's already been deduplicated
and its price is already in USD. q09–q11 should not need to know either of
those rules exist.
