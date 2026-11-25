# Hint 3

Group the in-range snapshots by source and truncated hour. Compute the count and
share while you still have only real observation rows. After joining those results
to the full set of keys, fill in missing counts and leave missing shares as `NULL`.
