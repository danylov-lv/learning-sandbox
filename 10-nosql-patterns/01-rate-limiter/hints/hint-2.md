Three atomic building blocks, roughly in order of "how much they hand you
for free":

**1. `EVAL` / a Lua script.** Redis runs a Lua script server-side as a
single atomic unit -- no other client's command can be interleaved between
any two lines of your script, because Redis is single-threaded for command
execution and a script runs to completion before the next command (from
anyone) starts. This is the most general option: inside the script you can
read, compare, and write in one shot, so whatever "check and record" logic
you want, the atomicity is free as long as it's all in the script. The
tradeoff is you're writing Lua, and the script has to be self-contained --
it gets the keys/args it needs passed in, and it can't reach back out to
your Python process mid-execution.

**2. Fixed window via `INCR` + `EXPIRE`.** `INCR` on a per-window key
(something keyed by resource AND the current window's identifier, e.g.
"which minute/second bucket are we in") already returns the post-increment
value atomically -- no separate GET needed at all. Compare that returned
value to `limit` (if it exceeds the limit, this call is over -- but note
you already incremented; think about whether that matters for your "don't
consume budget for a rejected call" requirement, and whether it does or
doesn't given what over-admission vs slight-undercounting means here). Set
an expiry on the key the FIRST time you create it (there's a Redis command
for "set expiry only if the key has none / this is the first write") so the
counter resets after the window without you tracking window boundaries by
hand. The tradeoff: a fixed window has a burst edge -- calls just before a
window boundary and just after it can together exceed `limit` within any
arbitrary `window_seconds`-long slice of real time, even though each
window's own count never does.

**3. Sliding-window log via a sorted set.** Keep a Redis sorted set per
resource where each member represents one hit and its score is the
timestamp it happened. On each `allow()` call: drop everything older than
`now - window_seconds` (`ZREMRANGEBYSCORE`), add the current hit
(`ZADD`), then count what's left (`ZCARD`). If the count is at or under
`limit`, admit; otherwise you need to undo the add you just made (or check
before adding -- think about ordering so you don't leave a phantom hit
sitting in the set for a rejected call). This gives an exact rolling
window with no burst edge, at the cost of unbounded-ish memory per resource
(bounded by `limit` once trimmed) and three commands instead of one. Note
that ZREMRANGEBYSCORE + ZADD + ZCARD are three separate round trips unless
you either wrap them in something atomic or accept that, run as three
separate calls, the race from hint-1 comes right back.

Whichever you pick, the validator doesn't care -- it only observes
`allow()`'s return values.
