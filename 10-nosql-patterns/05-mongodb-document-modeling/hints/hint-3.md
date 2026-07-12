Once your indexes and pipelines are written, don't just trust the validator
-- open a shell yourself (`mongosh` against port 27310, or a quick Python
one-liner via `harness.common.mongo_db()`) and run
`db.t05_products.find(<your filter>).explain("queryPlanner")` on the exact
filter shape `graded_query()` and `nested_color()` use. Look at
`queryPlanner.winningPlan`: you want to see a `FETCH` (or the query itself)
wrapping an `IXSCAN` stage naming the index you built, and you want to NOT
see a `COLLSCAN` stage anywhere in that tree. If you see `COLLSCAN`, the
index you created doesn't match the query's filter shape closely enough for
the planner to pick it -- check the field order and whether every field the
filter touches is actually part of the index you built. Also check
`rejectedPlans` if present; a plan can exist and still lose to a full scan
if the planner's cost estimate favors the scan (rare here, but worth
knowing this list exists).

Separately, think about `seller`. Right now it's embedded: `{seller_id,
name, rating}` sitting inside every product document that seller sold. That
means if a seller's rating changes, or their name changes, you'd need to
update it in every one of their product documents -- for a seller with a
handful of listings that's nothing, but imagine a seller with 50,000
listings on a much bigger version of this catalog. When would you pull
`seller` out into its own `t05_sellers` collection and reference it by
`seller_id` instead of embedding the whole thing? What do you gain (single
place to update a seller's data, smaller product documents), and what do you
lose (every query that needs seller info alongside product info now needs a
second round trip, or a `$lookup` join, instead of reading one document)?
There's no code to write for this -- it's a modeling judgment call worth
having an actual opinion on, and it's exactly the kind of question the
write-up task later in this module (07) will ask you to argue both ways.
