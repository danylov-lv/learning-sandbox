# Hint 1

"Pick the latest row per group" always needs two ingredients: a grouping key and a
total ordering within that group. If two rows are equally "latest" under your
ordering, the ordering is incomplete — add another column until no two rows in any
group can ever tie.

Solve step 1 (the dedup) completely before touching step 2 (the aggregation). If you
try to do both at once you'll have no way to check the dedup is actually
deterministic.
