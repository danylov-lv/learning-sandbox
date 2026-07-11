Task 03 proved an idempotent upsert survives redelivery on its own -- that's
why it's easy to miss the danger here. `replica.offers` will look correct no
matter how many times a message replays, so it's tempting to think the whole
consumer is "done" once that part works.

`mart.t06_meta.applied_changes` is a different kind of state. It's not a
mirror of the source you can re-derive by re-applying the same input twice;
it's a count of how many times you've done work. `applied_changes += 1` run
twice for the same event is not a duplicate you could spot in the table --
it's just a number, one that's silently too high, indistinguishable from a
correct count computed from a slightly different (shorter) stream.

The place this shows up is the same crash window 07/04 taught you to worry
about: the mart transaction has committed (so the upsert AND the increment
already happened), but the Kafka offset commit that would have told the
broker "don't redeliver this" never went out before the process died. On
restart, the same event arrives again. Ask yourself: what, in your design,
stops the *second* arrival of that event from touching `applied_changes` at
all -- given that the first arrival's mart transaction already fully
committed?
