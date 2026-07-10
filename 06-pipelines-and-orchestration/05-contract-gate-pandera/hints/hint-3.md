# Hint 3

Rough shape for the DAG, one task per stage (or fold stages together if you
prefer — the validator only cares about the end state in the two tables, not
your task boundaries):

1. `extract`: `SELECT dt, line_no, payload FROM staging.price_records_raw
   WHERE dt = %s ORDER BY line_no`. Build a pandas DataFrame from the jsonb
   payloads — `pd.json_normalize` or a plain list-of-dicts constructor both
   work, the payload's keys become columns. Keep `line_no` alongside as a
   non-schema column you can use later to map failures back to source rows
   (which means it can't go through the strict pandera schema as-is —
   validate only the payload columns, carry `line_no` separately and rejoin
   by index afterward).

2. `validate`: call your schema's `.validate(df, lazy=True)`. On success,
   everything passed — that's your `core` batch, no `failing` rows. On
   `SchemaErrors`, `err.failure_cases` gives you the failing row indices;
   pandera's `.validate(..., lazy=True)` also gives you (via the exception
   or a separate call) which rows overall failed at least one check. Split
   `df` into `passing = df.drop(failed_indices)` and `failing = df.loc[failed_indices]`.
   For the quarantine `reason`, group `failure_cases` by row index and join
   the check names/columns into one string per row — doesn't need to be
   fancy, just informative enough that a human reading `ops.quarantine`
   later understands why.

3. `load_core`: build a plain `INSERT INTO core.price_records (...) VALUES
   (...) ON CONFLICT (source_site, product_url, scraped_at) DO NOTHING` (or
   `DO UPDATE SET ... `, your call) executed via `psycopg`'s
   `executemany`/`copy` for the passing batch. `dt` is a column value here,
   not a `WHERE`-scoped delete target, so you don't need to delete anything
   first if you're using the conflict clause correctly — but double check
   that a full rerun of an already-loaded day doesn't produce a different
   row count than the first run.

4. `load_quarantine`: for the failing batch, either delete existing
   `stage='contract'` rows for this `dt` first and then insert fresh (simple,
   works fine for this task's scale), or key quarantine rows on something
   stable (e.g. `(dt, stage, line_no)`) and upsert. Both are legitimate;
   delete-then-insert is simpler to reason about and this table isn't huge.

For the absurdity ceiling on `price`: a single flat number cannot work.
An absurd price for a cheap category (a few hundred for something that
normally costs single digits) is still far below a completely normal price
for an expensive one — a flat ceiling either lets the cheap-category junk
through or rejects legitimate expensive items. The ceiling has to be
per-category. You don't need anything statistical to find the values: dump
each category's prices from a few days of staging data, sort them, and look
at the top of the distribution — the legitimate tail ends, then there's a
wide empty gap (multiples, not percent), then an isolated cluster of junk
an order of magnitude out. Any ceiling inside that gap is correct; round
numbers are fine. Express the rule as a DataFrame-level check (pandera's
per-Column `Check` only sees its own column; comparing `price` against a
ceiling looked up by `category` needs a `Check` at the schema level or a
mask computed outside the schema, same as the `scraped_at` day-window
rule).
