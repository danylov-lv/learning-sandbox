A concrete walk-through for ONE strategy -- sliding-window-log, done as a
single Lua script so the three sorted-set operations are genuinely atomic
as a unit (not the earlier warning about running them as separate round
trips):

1. Build the Redis key for this call from `self.namespace` and `resource`
   (something like namespace + resource, so different resources land on
   different keys and different tasks never collide).
2. In the script, compute the window's lower bound: the current time minus
   `window_seconds`. You need "now" available to the script -- Lua's own
   clock functions aren't safe to rely on for this inside Redis scripting,
   so pass the current time IN as an argument from Python at call time,
   rather than trying to compute it Lua-side.
3. First step in the script: remove every member of the sorted set whose
   score is older than that lower bound. This is what makes the window
   "slide" -- old hits age out on every call, not just at fixed boundaries.
4. Count what's left in the set. If that count is already at `limit`,
   this call is rejected -- return without adding anything (a rejected call
   must not consume budget, so don't add its own hit to the set in this
   branch).
5. Otherwise, add a new member for this call (its score is "now"; its
   member value needs to be unique per call, since sorted-set members are
   deduplicated by value -- two hits at the exact same timestamp would
   collapse into one member if you used the timestamp alone as the member).
   Then this call is admitted.
6. Set an expiry on the key itself (something a bit longer than
   `window_seconds`) so a resource that stops being hit doesn't leave its
   sorted set sitting in Redis forever.
7. Run all of the above as one script via the client's `eval` (or
   equivalent), passing the key, the current timestamp, `window_seconds`,
   and `limit` in as arguments -- don't hardcode any of them into the
   script body itself.

The tradeoff worth writing down in your NOTES: this gives you an exact
rolling window (no burst edge across boundaries), at the cost of one sorted
set per resource whose size is bounded by `limit` (not by total request
volume, since old entries keep aging out) and a slightly heavier script
than a plain fixed-window `INCR`. A fixed-window `INCR` + `EXPIRE`
implementation is simpler and cheaper per call, but allows up to roughly
`2 * limit` requests within some `window_seconds`-long span that straddles
two fixed windows -- worth knowing which one you actually built and why.
