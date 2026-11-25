# Hint 1 -- direction

This capstone is not a new mechanism either -- like every capstone in this
sandbox, it's an existing set of mechanisms recombined into something that
has to actually survive being used together. Decompose the story into
stages, and each stage maps onto a task you've already seen (even if you
haven't done that task's own scaffold yet, its README explains the
mechanism -- reading a README is not the same as copying its code, and
that's explicitly allowed here):

- **Intake / rate shaping** -- task 01's atomic rate limiter is the pattern
  for "don't let one domain's scrapes overwhelm anything downstream." This
  capstone's checkpoints don't actually call a rate limiter (CP1/CP2 need
  the FULL event stream to converge to ground truth), but DESIGN.md asks you
  to reason about where it WOULD sit in a real deployment of this control
  plane.
- **The durable handoff** -- a Redis Stream plus a consumer group (task 04's
  territory) is the queue: `produce` writes to it, one or more consumers
  read from it via `XREADGROUP`, and every read is remembered in a Pending
  Entries List until `XACK`ed. That PEL is the entire reason recovery is
  possible: a crash doesn't lose the fact that a message was delivered, it
  just leaves it un-acked.
- **The materialization** -- turning a stream of raw observations into a
  current-state view in MongoDB, keyed by product_id, keeping only the
  latest observation. This is the part that has to be idempotent, because
  everything upstream of it (the stream, the consumer group, the reclaim)
  only promises AT-LEAST-once delivery, never exactly-once.

The genuinely new idea this capstone is built around: at-least-once
delivery is a solved, well-understood primitive (that's what Redis Streams
consumer groups give you for free). The hard part was never "how do I make
sure every message gets delivered" -- it's "how do I make REDELIVERY safe,"
which is a property of your materialization logic, not of the queue. Get
that one function right and the crash-recovery story falls out for free.
