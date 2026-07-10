# Hint 2

For the three feature requests:

1. **Multi-reader (analytics team wants their own independent copy)**: In RMQ, you'd need a second queue and a separate exchange binding, doubling infrastructure. In Kafka, task 01 showed you that two consumer groups read the same topic independently, each tracking its own `offset`. That's replay and independent consumers for free—no extra queues needed. Map this explicitly to your answer.

2. **Replay (pricing ML model rerun)**: RMQ has no "read from offset 0 again"—acks delete messages. Task 02 and 08 showed you `offset` management and how a consumer can jump to an old offset and re-read. What would a scraper farm need to do in RMQ to replay? (Spoiler: save messages to cold storage, or never ack and manually replay from a dead-letter exchange.)

3. **Consumer groups** (ops wants independent progress tracking per category): Task 03 showed you partition assignment and rebalancing within a consumer group. In RMQ, competing consumers all pull from the same queue and none track independent state—there's no "consumer group" concept. Task 06 showed you monitoring lag per group; task 08 showed you exactly-once guarantees within a consumer group transaction.

For "WHERE NOT TO MOVE": Task 01–08 all assume a deterministic 6-partition setup. What happens if you suddenly need 20 competing spider processes? In RMQ, spin up 20; they all share work elastically. In Kafka, you're capped at 6 partitions (one consumer per partition max). This is the tradeoff.

Also consider: Kafka is a cluster to run and monitor; RMQ is a single broker. Operational burden matters.
