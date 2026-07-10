# NOTES

## Log vs queue: written comparison

<!-- Required section, graded by the validator (min ~600 chars of real content,
     must discuss offsets, acks, consumer groups, competing consumers, and
     replay by name). Delete this comment and write your own comparison,
     grounded in what you actually observed running producer.py and
     read_history.py against s07.t01.price-updates. Cover at least: -->

<!-- - Log vs queue: what "append-only, retained" means for a Kafka topic
     partition versus what happens to a message in RabbitMQ once it's
     delivered and acked. -->

<!-- - Offset vs ack: what an offset is (a per-partition cursor position a
     consumer tracks) versus what an ack is (a per-message acknowledgement
     the broker tracks) — and why that difference is what makes replay
     possible in one model and not the other. -->

<!-- - Consumer group vs competing consumers: what running read_history.py
     twice under two DIFFERENT group ids showed you, versus what a pool of
     RabbitMQ consumers competing for the same queue would have done with
     the same 200k messages. -->

<!-- - Why replay is possible in Kafka and not RabbitMQ: connect this back to
     retention and offsets — what would have to be true of RabbitMQ for
     "replay last hour's stream through a new consumer" to work there? -->

(fill in)

## What I learned

(fill in after completing the task)

## Gotchas

(fill in after completing the task)

## Open questions

(fill in after completing the task)
