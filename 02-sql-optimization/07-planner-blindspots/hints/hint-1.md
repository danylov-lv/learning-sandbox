# Hint 1

Run `EXPLAIN (ANALYZE, BUFFERS)` on `src/given_query.sql`. Walk every node
and compare its estimated row count to its actual row count (remember to
account for loops on parallel nodes — actual rows is reported *per loop*).
One node's estimate is off by four orders of magnitude. Which one, and
what predicate is it evaluating?
