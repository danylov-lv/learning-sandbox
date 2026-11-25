# Hint 1 -- direction

Think about what "check, then increment" actually means when it's two
separate operations against shared state.

A naive limiter reads the current count for a key, compares it to the
limit, and -- if it's under -- writes back count+1. That's fine as long as
requests are serialized. But this API runs as multiple stateless workers,
and even within one worker, an async handler awaits the Redis round trip in
between the read and the write. During that gap, other requests for the
same key can run their own read.

Picture ten requests for the same fresh key landing at (almost) the same
instant, with a limit of ten. Every one of them can, in principle, read
"count = 0..9, under the limit" before any of them has written its
increment back. If eleven or twenty arrive at once, the same thing happens
-- they all see a stale, still-under-the-limit count and all get admitted.
The limit was never actually enforced; only the *final* stored value
reflects reality, and by then it's too late.

So the read and the write can't be two things. Whatever you build, ask: is
there a moment where a decision is made based on state that could change
before that decision is durably recorded? If yes, that's the gap where a
concurrent burst walks through.

Before reaching for a specific algorithm, get comfortable with that framing:
a limiter is really about *reserving a slot*, not about *checking a
number*. Reserving implies the read and the write are the same atomic step.

Also notice the task has two of these to enforce, on different timescales
(a tight window for bursts, a longer one for sustained use) -- keep the
race-condition problem separate in your head from the "two tiers" problem;
you'll want to solve the atomicity question once and then apply it twice.
