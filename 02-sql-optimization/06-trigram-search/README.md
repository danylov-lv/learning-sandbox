# 06 — Trigram Search

## Backstory

"The real search service was never finished" is the kind of sentence that
ends up in a postmortem. Right now the header search box on Kupitron runs a
plain `ILIKE '%term%'` against `products.title`, and it is the single most
complained-about thing in the last NPS survey. You've confirmed it in
`queries/q06.sql`: a substring search for `titanium` that has to look inside
every one of 2.0M titles, because the pattern starts with a wildcard.

You know Postgres has *some* index for text, since `q03` and `q05` both got
fixed with the right index type for their operator. This one is different
again — neither of the tricks you've used so far apply to `LIKE '%x%'`.

## What's given

- `seed/schema.sql` — the live schema (read-only reference; do not edit, do
  not run it against the DB).
- `queries/q06.sql` — the canonical, screaming query. **Do not modify this
  file.**
- `tools/plan_check.py`, `tools/baseline.py`.
- The live Postgres instance; `products` has 2.0M rows.
- `src/fix.sql` — empty stub. You write your fix here.

## What's required

1. Record the baseline once:

   ```
   uv run python tools/baseline.py record queries/q06.sql
   ```

2. Work out why a B-tree index on `title` (even one built for `LIKE`
   prefix matching) cannot help a pattern with a leading `%`.
3. Find the extension and index type built for arbitrary substring search,
   and write the DDL into `06-trigram-search/src/fix.sql`. This is the one
   task in this module where the fix needs a `CREATE EXTENSION` as well as
   a `CREATE INDEX` — both belong in `fix.sql`.
4. Apply it against the live database yourself.
5. Only `order_items`, `products`, `reviews` (and read-only FK joins) may be
   touched. Leave `orders`, `users`, `payments`, `inventory_events`,
   `sellers`, `categories` untouched.

## Completion criteria

Run, from the module root:

```
uv run python 06-trigram-search/tests/check.py
```

The checker verifies:

1. No `Seq Scan` on `products` in the `q06.sql` plan.
2. A `Bitmap Index Scan` is present.
3. The query runs meaningfully faster than your recorded baseline.

If the required extension isn't installed yet, the checker will tell you
that directly — that's expected, not a bug: installing it is part of the
fix.

## Estimated evenings

1

## Topics to read up on

- Why B-tree indexes only accelerate `LIKE`/`ILIKE` patterns anchored at the
  start of the string (and how locale/collation affects even that)
- Trigrams: what they are, how `pg_trgm` builds them from text
- GIN (or GiST) indexes with `gin_trgm_ops` for substring and similarity
  search
- `CREATE EXTENSION` — what it actually installs, and why it needs to run
  once per database
