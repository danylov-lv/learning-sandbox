# Hint 2

For Parquet: pyarrow has a writer object that accepts one batch of rows at
a time and appends it to the file, closing out row groups as it goes —
you never need a single in-memory `pa.Table` holding the whole dataset.
Building each batch means constructing arrays with an *explicit* schema you
define once (a `pa.schema([...])` listing all 13 columns with their exact
types) rather than letting anything infer types from a sample of rows. For
the `captured_at` column specifically, you need to turn the ISO-8601 `...Z`
string into something pyarrow will store as a real timestamp column with a
UTC timezone attached — think about what Python stdlib gives you for
parsing an ISO string into a `datetime`, and how pyarrow expects timestamp
values to be handed to it (a list/array of `datetime` objects works, but
check what timezone-awareness it needs to produce `tz=UTC` in the output
schema).

For nested `attrs`: don't try to project it into a fixed set of Arrow
struct fields — its keys vary row to row. Re-encode the whole dict as a
JSON string and store that as a plain string column; that's a legitimate
Parquet design choice (semi-structured column as text) and it's exactly
what the contract asks for here.

For CSV: the standard library's `csv` module writer handles quoting fields
that contain commas, quotes, or newlines automatically — you don't need to
escape `attrs` (which will contain both commas and quotes) by hand. Look at
what value to pass for a `None` price or a `None` in_stock so the writer
emits an empty field rather than the string `"None"`.
