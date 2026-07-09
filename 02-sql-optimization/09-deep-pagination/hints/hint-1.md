# Hint 1

Run `EXPLAIN (ANALYZE, BUFFERS)` on `src/given_query.sql`. Find the node
that does the sorting/scanning and look at its `Actual Rows` compared to
what actually gets returned to the client (100 rows). What is `OFFSET
800000` actually asking the executor to do, mechanically, once it has rows
in the right order? Does raising the offset change the amount of *work*,
or only the amount of *work that gets thrown away*?
