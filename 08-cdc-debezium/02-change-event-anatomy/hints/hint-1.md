An envelope is `{"schema": ..., "payload": ...}`. `decode_value()` already
strips the outer layer for you, so what your code sees is the payload:
`op`, `before`, `after`, `source`, `ts_ms`. `before` is the row as it was
before the change (`None` for inserts and snapshot reads), `after` is the
row as it is now (`None` for deletes). `source` carries where in the WAL
this event came from -- worth printing a few of these by hand and looking
at the shape before you write any logic.

Now look at `after["price"]` on an update event. It is not a JSON number.
Why would a column typed `NUMERIC(12, 2)` in Postgres NOT show up as a
plain number in JSON? What does the Kafka Connect converter have to choose
between when serializing an arbitrary-precision decimal into a format
(JSON) that only has IEEE-754 doubles as its native number type?
