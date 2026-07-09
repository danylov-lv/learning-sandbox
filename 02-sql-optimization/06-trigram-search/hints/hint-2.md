# Hint 2

`pg_trgm` is a contrib extension that breaks text into overlapping
three-character sequences ("trigrams") and can index those. A GIN index
built with the `gin_trgm_ops` operator class lets Postgres answer "which
rows have title text sharing enough trigrams with 'titanium'" using the
index, then confirm the actual substring match on the smaller candidate
set — instead of applying `ILIKE` to all 2.0M rows.

The extension has to be created before the operator class exists to build
the index against.
