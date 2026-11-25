The bug in the original implementation isn't in the aggregate function —
it's in how the window's boundary is defined. "Last 30 days" and "last N
rows" are the same thing only when snapshots arrive on a perfectly regular
schedule. This data doesn't. Look for the frame clause that lets you bound a
window by a span of the ordering column's values, not by a row count.
