# RMQ vs Kafka — Production Pipeline Analysis

Fill in each section with your own analysis of the scraping pipeline you described in the README and how the concepts from this module apply to it.

## The current RMQ pipeline

Describe your current production setup: the Scrapy spiders (producers), the RabbitMQ queues or exchanges they feed, which consumers (downstream processes) pull from them, how messages are acknowledged, and what happens to messages when a consumer dies mid-process.

## Where Kafka would help

Map each real capability gap in your current RMQ setup to a concrete Kafka feature you learned in this module. Be specific: when and why would you use each (replay from offset, consumer groups for independent readers, log compaction for latest-state, lag monitoring for backpressure, etc.)?

## Where Kafka would NOT help / would be overkill

What does RMQ do better for your pipeline, or do cheaper? List the genuine RMQ strengths — per-message routing rules, priorities, direct task queues, competing-consumer load-balancing without partition ceilings, operational simplicity — and explain why each matters to your scraper.

## The partition-count / ordering tradeoff

Kafka guarantees order within a partition but forces you to choose a partition count at topic creation. RMQ competing consumers scale elastically to any number of workers without topology constraints. How would this tradeoff affect a decision to move parts of your pipeline? Draw a concrete example from your scraper.

## Migration verdict

If you actually had to redesign the scraper pipeline tomorrow, what would you move to Kafka and what would you keep in RMQ, and why? Write the one-sentence rule you'd tell a teammate who asks "should I use Kafka or RMQ for this new component?"
