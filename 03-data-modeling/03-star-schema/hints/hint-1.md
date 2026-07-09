# Hint 1

Start by writing down the grain of the fact table in one sentence, before
any DDL: "one row per _____." If you can't finish that sentence precisely,
you don't know what a row in `fact_price_observation` means yet, and any
DDL you write will drift as you go. (The grain here is fixed by the
question contract: one row per deduplicated observation.)

Once the grain is fixed, ask what the fact row needs to point at to answer
q09–q11 without leaving `mart`: a time bucket, a product's category/brand,
a shop's country/tier. Each of those is a dimension.

Why surrogate keys instead of joining on `shop_code` / `product_code`
directly? Because a dimension row here is not "the shop" — it's "the shop
as it was during some interval." The same `shop_code` legitimately has
multiple valid rows in `dim_shop` over time (gold now, silver last year).
A surrogate key identifies one specific version of one entity; the natural
code alone can't do that.

That leads to the central design decision of this task: *when* do you
figure out which dimension version an observation belongs to? You could
defer it to query time (join fact to dim with a range predicate every time
you query) or resolve it once, when you load the fact table, and store the
resolved surrogate key. The whole point of this exercise is to notice which
of those two is actually doing the work, and to choose the one that makes
q09–q11 trivial.
