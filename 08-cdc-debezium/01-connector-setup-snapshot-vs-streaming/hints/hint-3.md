Concretely:

1. `build_config()` returns `{"name": "s08-t01", "config": {...}}`. Build
   the `config` dict as described in hint 2 -- every value is a JSON
   string, including the port. `main()` already does
   `register_connector(build_config())` followed by
   `wait_for_connector_running("s08-t01")` for you.
2. Register it (`uv run python src/register.py`) and watch it reach
   `RUNNING`. At that point the connector has already started its snapshot
   -- on a 20k-row table this finishes in a couple of seconds, so by the
   time you look, both phases may already be behind you.
3. To actually observe the two phases as distinct: drain
   `s08.t01.shop.offers` from the beginning right after registering.
   Decode every value with `decode_value()`, get `(op, before, after)` via
   `change_op()`, and count how many events have `op == "r"` -- that count
   should equal `shop.offers`'s row count exactly. Those are all snapshot
   events; none of them have a `before` (there's no "previous version" of
   a row Debezium is seeing for the first time).
4. Now, separately, apply an INSERT, an UPDATE, and a DELETE directly
   against `shop.offers` via `psycopg` (not through Debezium -- Debezium
   only reacts). Drain the topic again from the beginning. You should see
   three new events with `op` values `"c"`, `"u"`, `"d"` respectively,
   appearing after all the `"r"` events. Check the `"u"` event's `before`
   -- it should be the *entire* old row (every column, old price included),
   not just the primary key. That's `REPLICA IDENTITY FULL` (already set
   on `shop.offers` by the module's schema) at work; without it, `before`
   on an UPDATE/DELETE would only carry the primary key.
