Auto-commit was easy because you never had to think about the moment
between "I did the work" and "I told the broker I did the work". With
`enable.auto.commit=False` that moment is now yours to place, and it's the
only decision this task is testing.

There are exactly two things that happen per message: you write to
`ops.t02_seen`, and you commit the offset. A crash can land between them.
Ask yourself, for each of the two possible orderings, what the consumer
sees on restart: does it resume at an offset whose message was written, or
one whose message wasn't? Does that produce a gap (a seq that never
appears) or a repeat (a seq that appears twice)? The task is graded on
whether gaps can happen -- repeats are fine.

Don't touch `_maybe_crash` beyond calling it once per message at the spot
you decide is "right after processing". It already does the crashing.
