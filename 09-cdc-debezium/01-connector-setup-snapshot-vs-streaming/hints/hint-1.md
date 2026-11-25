A brand-new Debezium Postgres connector doesn't start by tailing the
write-ahead log. Before it can stream anything live, it needs to know
where "live" begins -- and for a table that already has rows, that means
reading the current state first. Two phases, one after the other:
read-everything-once, then stream-everything-new. There's a connector
setting that controls whether that first phase happens at all.

You don't run Debezium as a standalone process here -- it's a plugin
inside a Kafka Connect worker, and Kafka Connect workers are configured
and controlled over a REST API, not a config file you hand to a CLI. Go
look at what `harness.common.register_connector()` actually does with the
dict you give it.
