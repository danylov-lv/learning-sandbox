# Hint 2 -- naming the pieces

The pattern you want is called an **idempotency key**, and it's the same
mechanism real payment APIs (Stripe, etc.) use for "the client isn't sure if
its POST went through, so it retries with an identifier that says 'this is
the same logical request as before, not a new one.'"

The API contract:

- A request carrying an `Idempotency-Key` the server has never seen ->
  genuinely new work. Do it, and remember (durably) that this key now maps
  to whatever you created.
- The SAME key, seen again -> don't redo the work. Look up what that key
  already maps to, and hand back a reference to it (here: the same
  `job_id`). It doesn't matter whether the original request is still
  running or long finished -- the answer is "here's the job you already
  started," every time.
- A DIFFERENT key -> a completely unrelated request. It gets its own job, no
  relationship to any other key's job.

So "remembering" needs a place to live that survives past one request's
lifetime and is visible to every other request (and every worker) -- a
database row is the natural choice, keyed on the idempotency key itself.

Now the race. Picture the naive version: "`SELECT` for a row with this key;
if none, `INSERT` one." Under a single caller, sequential, this is
completely correct. Under N callers hitting a *fresh* key at the *same*
moment, it falls apart: nothing stops all N of them from running the
`SELECT` before any of them has run the `INSERT`. Every one of them sees
"no row" -- correctly, at the moment they looked! -- and every one of them
proceeds to create a job. The bug isn't in either step individually; it's
that there's a gap between them where the state can be exactly what N
different callers all read as "safe to create."

Closing that gap means the check and the write can't be two things a client
of the database issues as separate statements with a decision in between.
Postgres has a primitive built for precisely this: a `UNIQUE` constraint,
combined with `INSERT ... ON CONFLICT`. The constraint makes "does a row
with this key exist" and "create the row" resolve as ONE atomic operation
from the database's point of view -- multiple concurrent `INSERT`s racing
for the same unique value are serialized by Postgres itself; exactly one of
them can "win" and actually insert, and the rest are told, atomically, that
they lost the race. Your job is to catch that outcome and read back what
the winner created, rather than trying to prevent the race with application-
level logic (a `SELECT` first, a lock you manage yourself, a `time.sleep`) --
none of which close the gap the way a database constraint does.

Hint 3 spells out the exact SQL shape.
