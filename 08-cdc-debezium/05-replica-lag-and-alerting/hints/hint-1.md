"Replica lag" is not one number here -- it's the answer to "how far behind
is the replica" asked from two different vantage points.

From the Kafka side: the materializer consumer group reads
`s08.t05.shop.offers`. The topic keeps every message whether or not that
group has read it, so "how far behind" is a relationship between two
positions the broker tracks independently -- exactly the consumer-lag
question module 07's lag-monitoring task already answered.

From the Postgres side: Debezium reads the source's write-ahead log through
a replication slot. The slot is a bookmark Postgres itself maintains -- how
far the slot's reader (Debezium) has confirmed processing, versus where the
WAL currently is. This is a question a RabbitMQ queue simply doesn't have
an answer to, because a queue has no equivalent of "how many bytes of WAL
am I pinning on disk for a reader that might be behind."

Both numbers can move independently of each other. A monitor that only
watches one of them is blind to half of what "the replica fell behind" can
mean.
