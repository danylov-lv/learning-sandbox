# Hint 2

The per-order queries only need one piece of information the "orders"
query already gave you: the order id. Once you have all N order ids from
the first query, you don't need to go back to the database N more times —
you can ask for "all line items belonging to any of these order ids" in
one query, using `WHERE order_id = ANY(%(ids)s)` (or `IN (...)`) with the
full list of ids collected up front. Join `products` in that same query to
get titles, instead of doing it per-order.

The same idea applies to payments: one query, `WHERE order_id =
ANY(%(ids)s)`, gets you every order's payment row(s) in a single round
trip.
