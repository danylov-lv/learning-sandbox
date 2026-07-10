# Hint 3

Use this structure to ground your answer in the module's concepts:

**The current RMQ pipeline:**
- X Scrapy producer processes → exchange `prices` → queue `scraped_prices_raw`
- Y consumer processes (competing consumers) read and ack; no competing-consumer load-balancing across queues, just round-robin within one.
- On crash/requeue: message goes back to queue, retried.
- No concept of "independent groups" — all consumers pull from the same queue at the same rate.

**Where Kafka helps (cite task numbers where you learned this):**
- Multi-reader (analytics reads live prices at their own pace, doesn't interfere with scrapers): task 01 showed consumer groups. Write: "Task 01 proved two consumer groups read the full log independently; in RMQ you'd need a mirror queue."
- Replay (ML team replays Tuesday 9am-11am): task 02 manual offsets + task 08 exactly-once. Write: "Task 02 showed jumping to offset 0 and re-reading; RMQ has no notion of offset—you'd need external state or log storage."
- Consumer groups (ops wants per-category tracking): task 03 rebalancing, task 06 lag per group. Write: "Task 03/06 showed consumer groups track offset independently; RMQ competing consumers share one high-water mark, not independent progress."
- Latest-state cache (always know the current price per product): task 07 log compaction. Write: "Task 07 compacted topic keeps only the last value per product; RMQ would require a side cache (Redis, Postgres) for the same thing."
- Backpressure monitoring: task 06 lag. Write: "Task 06 showed computing lag (HWM - offset); RMQ has no lag metric—you'd manual-instrument message age."

**Where Kafka is overkill / RMQ is better:**
- Simple task dispatch (spiders pulling work): RMQ queues are simpler than Kafka.
- Partition ceiling: with 6 partitions you can only have 6 consumers max (task 03 showed rebalancing); if your spider fleet grows to 20, you need to repartition the topic (expensive, impacts all consumers). RMQ spins up 20 consumers elastically.
- Operational complexity: RMQ is a single broker; Kafka is a cluster (ZooKeeper if older version, or KRaft if newer; leader/follower sync; controller election).
- Per-message priorities (if scrapers mark some jobs as urgent): RMQ has priority queues; Kafka doesn't.

**The partition tradeoff:**
Use task 03 (rebalancing) and task 04 (per-partition ordering): "Kafka orders messages within a partition (learned in task 04); I get 6 partitions by default. If I design for 6 scrapers concurrently and deploy 8 in production, 2 sit idle. If I scale down to 3 scrapers, 3 partitions are never used. RMQ spins up 20 competing consumers on the same queue without redesign."

**Migration verdict:**
"I'd move the analytics price stream to Kafka (multi-reader + replay benefits). I'd keep the scraper task dispatch in RMQ (simple, elastic scaling). The rule: if you need multiple independent consumers or replay, Kafka; if you need elasticity and low ops overhead, RMQ. If you need both, you're buying operational complexity you don't get back."

For NOTES.md: surprises could be "I didn't realize offsets are so different from acks until task 02" or "Log compaction solves the 'current state' problem I've always hand-coded" or "The partition-count ceiling bit me in production mental-modeling."
