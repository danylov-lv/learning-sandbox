Task 02 proved at-least-once delivery is survivable if all you're doing is
recording that a message arrived (duplicates were fine there -- the
validator counted DISTINCT seq). This task is harder because the side
effect is an AGGREGATE: `cnt += 1`. Applying that twice for the same event
is invisible in the table -- there's no row you can point to and say "this
one is a duplicate". The count is just wrong, silently, forever.

So the question isn't "when do I commit the Kafka offset" (you still do
that last, same as task 02) -- it's "how do I make sure a single event's
`cnt += 1; price_sum += price` runs at most once, even if I process the
same message twice because a crash happened between finishing the work and
committing the offset that would have prevented redelivery."

Two ways to get "at most once" out of work you might redo:

1. Give each unit of work a permanent, checkable fingerprint (the event's
   `seq` is already globally unique and already in every event you
   consume), and refuse to redo work whose fingerprint you've already
   recorded -- in the SAME transaction as the work itself.
2. Don't track "have I done this work" separately at all -- track "where
   did I get to" (an offset), and make the resume point that same
   transaction's business, not Kafka's.

Both turn "did the work, but might have crashed before telling Kafka" into
a non-issue, because neither one depends on Kafka's committed offset to
decide what's safe to (re)do.
