# Hint 2

The whole task lives in the `deltalake` package (`import deltalake`,
`pip`/PyPI name `deltalake`, this is `delta-rs` — no Spark or JVM
involved). Two entry points do essentially everything:

- `deltalake.write_deltalake(table_uri, data, ...)` — a free function that
  creates or writes to a table. Its `mode` argument (`"error"`, `"append"`,
  `"overwrite"`) controls whether it's the first commit, an additive
  commit, or a replacing commit. Each call to this function is one commit —
  that's the lever you pull to control how many commits a step produces.
  `data` doesn't have to be a single in-memory `pyarrow.Table`; anything
  that exposes the Arrow C Stream interface works, which includes a
  `pyarrow.RecordBatchReader` built from a Python generator. That's how you
  get "stream in, one commit out" for `initial_load` — one `write_deltalake`
  call, fed by a generator, rather than one call per chunk.
- `deltalake.DeltaTable(table_uri, version=...)` — open an existing table,
  optionally pinned to a historical version. This is your read side for
  everything: current state, time travel, schema at a version, row counts.
  Look at what it exposes for reading table state as an Arrow dataset, for
  inspecting the schema, for listing which partition values currently have
  live files, and for the commit history (each entry tells you the
  operation type and, for writes, whether it was an append).

For schema evolution and file maintenance, a `DeltaTable` instance exposes
namespaced sub-objects rather than flat methods — look for something like
`.alter` (schema changes: adding columns without touching data) and
`.optimize` (file compaction). Vacuuming (actually deleting files that
compaction or overwrites made obsolete) is a method on `DeltaTable` itself,
and it has a safety default that will refuse to delete anything recent
unless you explicitly override it — read what happens if you call it with
its defaults on a table you just modified.

For the MinIO leg: `write_deltalake`/`DeltaTable` both take a
`storage_options` dict for non-local URIs. AWS S3 environment variable
names are the vocabulary delta-rs expects here (endpoint, access key,
secret key, plus flags for "this isn't real AWS, don't assume HTTPS / don't
assume rename semantics"). `harness.common` has the MinIO endpoint helper
and credentials this module already uses for other tasks — reuse it rather
than hardcoding another copy of `sandbox`/`sandbox123`.
