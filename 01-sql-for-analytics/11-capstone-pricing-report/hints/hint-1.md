# Hint 1

Break the problem exactly along the checkpoint boundaries in the README and validate
each one standalone in `psql` before combining them. Do not write this as one
1000-character query from scratch — build it CTE by CTE, checking row counts and a
handful of sample rows at each stage.

Three separate hard parts are bundled here: walking a tree to its root, looking up a
time-varying rate as of a specific date, and comparing a value to "the same group's
previous period." Each has a standard SQL technique. Solve them one at a time.
