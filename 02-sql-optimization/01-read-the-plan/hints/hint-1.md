# Hint 1

Run `EXPLAIN (ANALYZE, BUFFERS)` on `queries/q01.sql` exactly as it stands
today. Find the node that touches `orders`. What kind of node is it, how
many buffers did it read, and how many rows did it actually return
compared to how many it scanned?

`\d orders` shows what indexes exist today. Is either of them built on the
columns this query actually filters and sorts by?
