Start from the mental model, not the API. In RabbitMQ, "consuming" a message
removes it from the queue's future — that's what an ack means. In Kafka,
"consuming" a message never removes anything; a consumer just moves its own
private bookmark (the offset it has committed) forward through a log that
keeps existing regardless. That's why the group id matters so much: the group
id is the *name of the bookmark*. Two different group ids are two different
bookmarks into the same unchanged log, so of course both see everything —
nothing was ever claimed or removed on the first read. The same group id used
twice is the *same* bookmark, so the second run starts from wherever the first
one left off.

For the producer, don't overthink the "create the topic" step — it's one
`harness.common.create_topic(...)` call or a few lines of
`confluent_kafka.admin.AdminClient`, and either is fine, it's not what this
task is testing. The part worth getting right is the produce loop itself:
what does `key=` need to be for `product_id` routing to work, and why does
`producer.poll(0)` need to run periodically rather than only once at the end
when you're producing 200k messages?
