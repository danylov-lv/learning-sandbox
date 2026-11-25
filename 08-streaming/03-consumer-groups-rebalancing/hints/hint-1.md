Think about what "subscribe" actually means in confluent-kafka versus what
you're used to from a RabbitMQ channel. `consumer.subscribe(topics)` alone
gets you messages, but it doesn't tell you *when* the set of partitions this
process owns changes underneath it. `subscribe()` takes two optional
callback arguments for exactly that — one fires when the coordinator hands
you partitions, one fires when it takes them away. Find them in the
confluent-kafka docs before writing anything.

Also think about the shape of the poll loop itself: it has to run
indefinitely (so the process stays a live group member the coordinator can
assign to) but still exit cleanly on a signal. What does "clean" mean here
for the rebalance you're trying to observe — what should happen to this
member's partitions the moment it shuts down?
