# 04 -- TTL and Lifecycle

## Backstory

Every day the scraper adds another day of price history, and nobody has
ever deleted a row. Eighteen months in, `observations_raw` is mostly cold
data nobody queries -- the dashboards care about the last few months, not
a scrape from a year and a half ago -- but it's still sitting on the same
expensive hot storage as this morning's rows. You want a retention policy:
anything older than 15 months should be dropped automatically, without a
cron job, a DELETE statement, or a human remembering to run one.

ClickHouse has this built in: a table-level `TTL` clause lets you say
"delete rows once `scraped_at` is older than N" directly in the schema,
and ClickHouse enforces it for you. The catch is *when*. A TTL is not a
background daemon sweeping the table every few seconds, and it is not
checked on every `SELECT`. It is evaluated **as part of a merge** -- the
same background process that combines small parts into bigger ones. Insert
500k rows into a table with a 15-month TTL and query it one second later,
and you will almost certainly see all 500k rows still there: nothing has
merged yet, so nothing has been checked against the TTL, let alone
deleted. In production this is fine -- merges happen constantly on their
own schedule (`merge_with_ttl_timeout` throttles how eagerly ClickHouse
retries TTL merges specifically) -- but it makes TTL impossible to observe
deterministically in a short script unless you know how to force it.

This task is about both halves: writing the TTL clause correctly, and
learning the one or two commands that force ClickHouse to actually apply
it right now, instead of waiting.

## What's given

- `src/ttl.py` -- four functions to implement, all currently `raise
  NotImplementedError`, prefixed `t04_`-style through the table name
  `t04_observations_ttl`:
  - `create_table_with_ttl(client)` -- create the TTL-bearing table.
  - `load_from_raw(client)` -- copy all of `observations_raw` into it.
  - `force_ttl(client)` -- make ClickHouse apply the TTL right now.
  - `surviving_count_query()` / `oldest_surviving_query()` -- SQL strings
    the validator runs to check what's left.
- The live stack: ClickHouse HTTP on `localhost:8309`, DB `price_history`,
  user/password `sandbox`/`sandbox`, and `observations_raw` already
  loaded (500k rows at this box's current scale, dated Jan-Jun 2025).
  `harness/common.py` gives you `ch_client()`, `ch_query()`,
  `ch_command()`.
- The retention window is fixed by this README: **15 months**, evaluated
  against `now()` at the moment the TTL is applied -- not against a fixed
  calendar date.

## What's required

Implement all four functions in `src/ttl.py`:

1. **`create_table_with_ttl(client)`** -- `DROP TABLE IF EXISTS
   t04_observations_ttl` then create it fresh: same 8 columns as
   `observations_raw`, `ENGINE = MergeTree ORDER BY (category, product_id,
   scraped_at)`, plus a table-level `TTL scraped_at + INTERVAL 15 MONTH
   DELETE`. Idempotent -- safe to call repeatedly.
2. **`load_from_raw(client)`** -- `INSERT INTO t04_observations_ttl SELECT
   * FROM observations_raw`, landing all rows. Nothing should be expired
   yet at this point: the TTL hasn't had a merge to act on.
3. **`force_ttl(client)`** -- force ClickHouse to actually apply the TTL
   against the current parts, so expired rows are physically removed
   before you query anything. There is more than one way to do this; see
   the docstring for the two documented mechanisms.
4. **`surviving_count_query()` / `oldest_surviving_query()`** -- return
   SQL strings (not query results): a `count()` over
   `t04_observations_ttl`, and a `min(scraped_at)` over the same table.

Try it by hand before trusting the validator -- create the table, load it,
query the count BEFORE calling `force_ttl`, then again AFTER, and watch
the number actually change:

```bash
uv run python -c "
from harness.common import ch_client, ch_query
import sys; sys.path.insert(0, 'src')
import ttl
c = ch_client()
ttl.create_table_with_ttl(c)
ttl.load_from_raw(c)
print('before force_ttl:', ch_query(ttl.surviving_count_query(), client=c))
ttl.force_ttl(c)
print('after force_ttl:', ch_query(ttl.surviving_count_query(), client=c))
print('oldest surviving:', ch_query(ttl.oldest_surviving_query(), client=c))
"
```

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It:

- Computes the expected surviving count **itself, live, against
  ClickHouse** -- `SELECT count() FROM observations_raw WHERE scraped_at
  >= now() - INTERVAL 15 MONTH` -- rather than trusting a static answer
  key. This is deliberate: `now()` moves every day, so the correct
  surviving count moves with it. The validator computes the cutoff the
  same way your table's TTL does, at the same moment it checks your
  table, so both sides always agree regardless of what day this runs.
  Sanity-checks that this expected count is neither 0 nor the full table
  (a non-trivial split) -- if that ever fails, it means the corpus's date
  range and "now" have drifted apart from this task's assumptions, and
  you'll get a clear message instead of a confusing wrong-answer failure.
- Drops any leftover `t04_*` table, then calls your
  `create_table_with_ttl` and `load_from_raw`.
- Calls your `force_ttl`.
- Asserts `surviving_count_query()` returns **exactly** the expected
  count computed above.
- Asserts that count is strictly less than the full 500k -- proof the TTL
  actually deleted something, not just a no-op.
- Asserts `oldest_surviving_query()` is no older than the same cutoff
  (`now() - INTERVAL 15 MONTH`, read fresh from ClickHouse) -- proof
  nothing that should have expired survived.
- Drops `t04_*` in a `finally`, whether the run passed or failed.

Fails cleanly (`NOT PASSED: <reason>`, exit 1, no traceback) if the stack
is down, a function still raises `NotImplementedError`, the surviving
count doesn't match, or anything older than the cutoff is still there.

## Estimated evenings

1

## Topics to read up on

- Table-level `TTL ... DELETE` in ClickHouse: syntax and semantics
- Why TTL is evaluated on merges, not on INSERT or on SELECT
- `OPTIMIZE TABLE ... FINAL` vs `ALTER TABLE ... MATERIALIZE TTL` -- what
  each one forces, and how they differ
- `merge_with_ttl_timeout` -- why ClickHouse throttles retrying TTL merges
  on its own, and what that implies for production tables you never force
- Column-level TTL vs table-level TTL (dropping a column's value vs
  dropping the whole row)
- `TTL ... GROUP BY` for rollups (aggregating old rows down instead of
  deleting them outright) -- worth knowing exists, not required here

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, and design rationale for every task in this module -- spoilers.
Don't read it before finishing this task.
