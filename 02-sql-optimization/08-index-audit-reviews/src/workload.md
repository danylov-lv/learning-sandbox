# Reviews table: read workload

This is what the application actually runs against `reviews`, gathered from
the query log. Nothing else touches this table.

## Read pattern 1 — product page, "recent reviews" widget

Every product detail page shows the 10 most recent reviews for that
product.

```sql
SELECT id, user_id, rating, review_text, created_at
FROM reviews
WHERE product_id = $1
ORDER BY created_at DESC
LIMIT 10;
```

Runs on every product page view. High volume, latency-sensitive (it's on
the critical render path).

## Read pattern 2 — rating summary widget

The same product page also shows a rating breakdown ("4 stars: 812, 3
stars: 240, ..."), computed live rather than cached.

```sql
SELECT rating, count(*)
FROM reviews
WHERE product_id = $1
GROUP BY rating;
```

Same volume as pattern 1 — it's rendered alongside it.

## Read pattern 3 — seller dashboard, review count

Seller dashboards show a running count of reviews received per product,
refreshed on dashboard load.

```sql
SELECT count(*)
FROM reviews
WHERE product_id = $1;
```

Lower volume than patterns 1 and 2 (dashboard traffic, not storefront
traffic), but not negligible.

## What the application does NOT do

- No query anywhere filters or sorts by `review_text` for exact or prefix
  match. There is no "search reviews by text" feature, no admin lookup by
  exact review body. Full-text moderation search, if it ever ships, would
  need a different index type entirely (not a plain B-tree on the raw
  column) — that hasn't been built.
- No query filters by `user_id` on this table directly (the "my reviews"
  page, if it exists, is out of scope for this workload).

## Write rate

Reviews are inserted continuously as orders complete and buyers leave
feedback: roughly 50-200 inserts/minute in steady state, bursting several
times higher during flash sales and end-of-season clearance events. There
are no `UPDATE`s or `DELETE`s on this table in the current application (a
review, once posted, is immutable) — the entire write cost is `INSERT`.
