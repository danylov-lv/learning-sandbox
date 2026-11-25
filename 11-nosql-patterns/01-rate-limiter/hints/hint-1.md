Start by naming the race precisely, because "just use Redis, it's fast" is
not an answer -- fast doesn't mean atomic.

`GET` is atomic. `INCR` is atomic. But "GET, then decide, then maybe INCR"
is three separate round trips from the client's point of view, and Redis
makes no promise about what happens to OTHER clients' commands in between
your GET and your INCR. If ten workers all call `allow("shop.example")` at
the same instant, all ten can execute their GET before any of them executes
their INCR -- all ten see the same "5 out of 50 used so far", all ten decide
"under the limit, admit", and all ten proceed to INCR. You wanted to admit
at most 45 more; you just admitted 10 more than you checked for, and if
this keeps happening, the domain's true request count blows past `limit`
while every individual check looked correct.

The fix is not "add a lock around the check" from the client side (that
just moves the race to whether you remembered to lock, and adds a whole new
failure mode: what if a worker crashes holding the lock?). The fix is to
ask: which single Redis command, or single atomic unit of commands, could
express "increment, and tell me the new value" or "add this hit, and tell
me how many hits are now in the window" without any other client's command
able to run in the middle? Go looking for that before touching
`src/limiter.py`.
