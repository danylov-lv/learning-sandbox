# Hint 3

One workable decomposition is three queries: (1) the user's orders, newest
first, limited; (2) all line items for those order ids, joined to
`products` for the title, ordered so you can group them back up
deterministically; (3) each of those orders' latest payment, one row per
order id (think about how you'd express "latest per group" — a window
function or `DISTINCT ON` are both reasonable). Reassemble in Python by
building a dict keyed by `order_id` from queries (2) and (3), then walking
the query-(1) order list and looking each order up in those dicts.

The alternative is to skip the Python-side reassembly entirely and have
Postgres return the whole nested structure from a single query, using
`json_agg`/`jsonb_build_object` to fold each order's items into a JSON
array server-side and a `LEFT JOIN LATERAL` (or a correlated subquery) to
pull in the latest payment per order. Either approach is acceptable — the
checker only cares about the final query count and the returned Python
structure, not which SQL shape you used to get there.
