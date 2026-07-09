# Hint 3

Two statements, in order:

```
CREATE EXTENSION pg_trgm;
CREATE INDEX ... ON products USING gin (title gin_trgm_ops);
```

After that, `ILIKE '%titanium%'` becomes eligible for a Bitmap Index Scan.
GiST with `gist_trgm_ops` is also a valid index type for the same operator
class if you want to compare the two, but GIN is the better default for a
mostly-read, occasionally-written column like `title`.
