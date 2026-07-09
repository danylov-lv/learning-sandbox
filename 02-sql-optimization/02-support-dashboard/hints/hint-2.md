# Hint 2

A composite index on `(user_id, created_at)` (in either direction on the
second column) serves an equality filter on `user_id` plus a *range*
filter on `created_at` just fine — the leftmost-prefix rule only cares that
`user_id` is pinned to a single value first. The index direction you chose
in task 01 for the `ORDER BY ... DESC` mattered for avoiding a sort there;
it does not block this query from using the same index, because `q02`
doesn't sort by `created_at` at all — it aggregates.

Check whether the plan for `q02` is already using your existing index
before writing new DDL.
