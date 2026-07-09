# Hint 1

Every index on `reviews` speeds up some read. But not every index is
*needed* to speed up some read — a composite index on `(a, b)` already
speeds up a query that filters on `a` alone, for the same reason a phone
book sorted by (last name, first name) already lets you find everyone with
a given last name without a separate index sorted by last name only.

Go through `src/workload.md` pattern by pattern and ask, for each of the
five existing indexes: which pattern, specifically, needs *this* index and
would break without it?
