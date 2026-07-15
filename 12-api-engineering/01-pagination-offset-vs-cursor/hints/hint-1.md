Start with the OFFSET endpoint and ask a concrete question: when Postgres
executes `... ORDER BY id LIMIT 20 OFFSET 199900`, what work does it actually
have to do to produce those 20 rows?

There's an index on `id` (it's the primary key), so the engine doesn't need
a full table scan to find where the ordering starts. But `OFFSET` is not
"jump to row N" -- it's "walk the ordered index from the beginning, and for
every row before the 199,900th, read it, count it, and throw it away."
Nothing you asked for is one of those 199,900 rows, yet all of them still
have to be produced and discarded before the engine reaches row 199,901.

That's the entire story: OFFSET's cost is proportional to *offset + limit*,
not to *limit* alone. Page 1 (`offset=0`) skips nothing, so it's cheap. Page
2,000 (`offset=199900`) skips almost the whole table to hand you the same 20
rows a page-1 request would return just as easily if they happened to sit at
the front. The rows you get back are never the expensive part -- the rows
you *don't* get back are.

So the fix has to avoid ever asking the database to skip N rows, no matter
how large N gets. The next hint names the technique and its query shape.
