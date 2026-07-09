# Hint 2

GIN (Generalized Inverted Index) indexes support the `@>` containment
operator on JSONB. You'll need `CREATE INDEX ... USING gin (attrs)`.

There are two operator classes for a GIN index on JSONB:
`jsonb_ops` (the default) and `jsonb_path_ops`. They differ in what they
index (every key and value vs. just value hashes down each path), which
affects both index size and which operators they support. Read up on the
tradeoff before picking one — both will satisfy the checker, but they are
not equivalent for every workload.
