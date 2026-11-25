The config dict `register_connector()` PUTs to Connect needs these keys to
be correct, not just present:

- `connector.class` -- which plugin class Connect should load
  (`io.debezium.connector.postgresql.PostgresConnector`).
- `plugin.name` -- the Postgres-side logical-decoding output plugin
  Debezium talks to. Use `pgoutput`, Postgres's own built-in one.
- `database.hostname` / `database.port` / `database.user` /
  `database.password` / `database.dbname` -- reachability, from inside the
  Compose network (hostname is the service name, `source`).
- `topic.prefix`, `slot.name`, `publication.name` -- this task's fixed
  names (see the README): `s08.t01`, `s08_t01_slot`, `s08_t01_pub`.
- `publication.autocreate.mode` -- so the publication gets created scoped
  to only the tables you list, not the whole database.
- `table.include.list` -- both `shop.offers` and `shop.products`.
- `snapshot.mode` -- the setting from hint 1 that decides whether the
  read-everything-once phase happens before streaming starts. You want the
  one that does both, in order.

Once the connector is `RUNNING`, the two phases are told apart on the
consumer side purely by the `op` field of each decoded event: `"r"` means
this row came from the snapshot; `"c"`, `"u"`, `"d"` mean it came from live
streaming. `harness.common.change_op()` gives you that field directly.
