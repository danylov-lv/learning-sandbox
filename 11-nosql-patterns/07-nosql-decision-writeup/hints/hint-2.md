# Hint 2

Go back to what task 06 actually forced you to build twice:

- The same semi-structured product documents, once in Mongo with a
  compound/multikey index, once in Postgres as a `jsonb` column with a GIN
  index and the `@>` containment operator. Did the two queries end up
  looking meaningfully different in shape, or did they converge on "filter
  on a couple of fields, one of them nested or array-valued"? If they
  converged, that's evidence for JSONB, not against it.

- What did you actually need Mongo's document model for that JSONB
  couldn't give you? Genuinely variable top-level shape per record (not
  just nested/array fields, which JSONB handles fine)? A native aggregation
  pipeline you find more readable than SQL? Or was it mostly familiarity?
  Be honest about which of these is a real technical advantage and which is
  a preference.

- Now go back to tasks 01-04. Could any of the rate limiter, lock, or dedup
  filter have been built directly in Postgres? Technically maybe (advisory
  locks exist, a table with a unique constraint can dedup). What would that
  cost you under concurrency that Redis's single-threaded command execution
  and native data structures (sorted sets, `SET NX`, Bloom) give you for
  free? That's the real "when NoSQL earns its place" argument for Redis —
  it's rarely about raw throughput.

Write one or two sentences per section that name a specific mechanism or
index shape you actually used, not a generality.
