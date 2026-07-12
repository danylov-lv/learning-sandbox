Start by naming the two ceilings separately, because "limit the requests"
is not one problem, it's two.

"How many requests are open right now" and "how many requests started in
the last second" are different quantities, and a mechanism that bounds one
does not automatically bound the other. A semaphore is very good at the
first: it caps how many coroutines can be inside a critical section
simultaneously, full stop. It has no concept of *time* at all -- it doesn't
know or care whether the last acquire happened a microsecond ago or ten
minutes ago, only how many holders currently exist. That's precisely why it
can't enforce a rate: if requests complete quickly, a saturated semaphore
will let go-and-reacquire happen as fast as requests finish, which can be a
much higher rate than you intended.

So before touching `src/fetcher.py`, get clear on the fact that you need two
independent gates, not one gate tuned harder. Sizing the semaphore smaller
does not fix a rate problem -- it just changes which of the two ceilings you
hit first (and can even make both worse, since a tiny semaphore forces
requests to serialize while each one still starts back-to-back the instant
the previous slot frees up).
