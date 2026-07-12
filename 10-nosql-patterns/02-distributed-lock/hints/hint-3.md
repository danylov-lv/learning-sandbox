Question 2 from hint-1 is the one a safe `release()` does NOT solve, and it's
what the fencing token is for.

Walk through the scenario slowly. Worker A acquires the lock and starts a
task -- say, writing a batch of results to some downstream store. Then A
stalls: a GC pause, the process gets swapped out, a slow disk write, whatever
-- something that takes longer than A's `ttl_ms`. While A is stalled, Redis
does exactly what a TTL means: it lets the key expire. Worker B now calls
`acquire()`, sees the key is gone, and legitimately takes the lock. B starts
its own task against the same downstream store.

Now A wakes back up. As far as A's own state is concerned, it still holds
the lock -- it never got an error, never got told "your lease is gone", it
was just asleep. A finishes its stalled write and sends it to the downstream
store. At this exact moment, BOTH A and B believe they are the exclusive
holder, and both are writing. A safe `release()` (hint-2) prevents A from
deleting B's Redis key when A eventually calls `release()` -- but it does
nothing about the write A already sent to the downstream store before that.
The downstream store has no idea a lock was ever involved; it just sees two
writes arrive from two different sources.

This is exactly the gap a fencing token closes -- but notice it can only
close the gap if the DOWNSTREAM resource participates: it has to be told the
fence number with every write, and it has to remember the highest fence
number it's seen so far and reject anything lower. Since `fence` is minted
by an atomically-incrementing counter at acquire time, and B acquired AFTER
A, B's fence is guaranteed higher than A's -- regardless of which one's
write physically arrives first, second, or how long either of them stalled.
The downstream store rejecting A's late, lower-fenced write is what actually
prevents the corruption; the lock and its safe release only prevent Redis's
own bookkeeping from getting corrupted, which is a different (necessary, but
not sufficient) problem.

When implementing the fence in `acquire()`, ask: does an `INCR` on a Redis
key give you a number that's safe to hand out even if it races against
another `acquire()` call happening at the same instant? What would happen
to fencing correctness if you generated the fence number in Python instead
(e.g. counting acquisitions locally, or using a timestamp)?
