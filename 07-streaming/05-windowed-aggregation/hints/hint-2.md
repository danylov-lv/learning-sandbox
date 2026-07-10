Parsing `event_ts`: it looks like `"2025-07-01T00:37:12.123Z"`. Python's
`datetime.fromisoformat` historically choked on the trailing `Z` (it wants
`+00:00`); check your interpreter version, or just do the string swap
yourself (`event_ts.replace("Z", "+00:00")`) before parsing, so you don't
depend on which Python you happen to be running. Whatever you parse must
end up as a timezone-AWARE datetime in UTC — comparing or subtracting a
naive datetime against `WINDOW_START` (which is aware) will raise, and
that's actually a useful guardrail, not an obstacle.

Flooring: `elapsed = event_dt - WINDOW_START` gives you a `timedelta`.
`timedelta` objects support floor division against another `timedelta`
(`elapsed // WINDOW_SIZE`) and that gives you an integer count of whole
windows. Multiply that integer back by `WINDOW_SIZE` and add to
`WINDOW_START` to get the window's start datetime. Three lines, no branches,
no special-casing "is this event late" — lateness is invisible to this
function, which is exactly the point: it treats every event the same way,
using only its own `event_ts`.

Upsert shape:

```sql
INSERT INTO mart.t05_window_category (window_start, category, cnt, price_sum)
VALUES (%s, %s, 1, %s)
ON CONFLICT (window_start, category)
DO UPDATE SET cnt = mart.t05_window_category.cnt + 1,
              price_sum = mart.t05_window_category.price_sum + EXCLUDED.price_sum;
```

Remember the psycopg gotcha for this stack's version: don't wrap the
upsert in `with conn:` expecting it to just manage the transaction — on
psycopg 3.3.4 here that context manager closes the CONNECTION on exit, not
just the transaction. Use `conn.cursor()` directly and call `conn.commit()`
yourself.
