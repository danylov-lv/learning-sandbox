# Hint 1

List the axes that actually differ between the three engines you've now
used on the same data — not "ClickHouse is fast" or "DuckDB is simple," but
the structural differences: does it run as a server you have to keep
alive? Does it support many concurrent readers, or is it built for one
process at a time? Does it want data pushed into it continuously, or does
it read files that already exist? Does it have a notion of automatic
lifecycle (TTL, background merges), or is everything manual?

For each axis, place Postgres, ClickHouse, and DuckDB on it based on what
you actually did in tasks 01-07 — not on reputation. Don't write the memo
yet. Just build the axes.
