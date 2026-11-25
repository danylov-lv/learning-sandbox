# Hint 1

You already built every piece of this. Task 03 taught you the
upsert-or-delete shape for `before`/`after` events. Task 04 taught you a
connector and a consumer both survive a source column being added
mid-stream, as long as you read new fields defensively. Task 05 taught you
what to measure to know a pipeline is keeping up. Task 06 taught you the
idempotent-dedup shape that turns Kafka's at-least-once redelivery into an
exactly-once effect on a Postgres table. This capstone does not ask you to
invent a fifth idea -- it asks you to compose the four you already have,
in the right order, inside one transaction per event.

"Converges" has a precise meaning here: after any sequence of crashes,
schema changes, and bursts, a live `SELECT` over `replica.offers` and a
live `SELECT` over `shop.offers` must describe the same rows. Keep that
one sentence in view while you write `apply_event_exactly_once` -- every
decision (what to dedup on, when to commit, how to read a maybe-missing
column) should be justifiable by whether it keeps that sentence true.
