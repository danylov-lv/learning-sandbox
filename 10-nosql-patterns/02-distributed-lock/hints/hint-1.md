`acquire()` is the easy half. `SET <lock key> <token> NX PX <ttl_ms>` does the
"is it free?" check, the "take it" write, and the expiry, all as one Redis
command -- there's no window for a second caller to sneak in between the
check and the set, so you don't need to reach for a Lua script here. Read the
`redis-py` docs for `SET`'s `nx=` and `px=` keyword arguments (or the
equivalent options on whichever client method you use) and think about what
the return value looks like on success vs. on "someone already holds it".

The actual danger in this task is not acquiring the lock -- it's everything
that happens afterward. Ask yourself two separate questions before you write
`release()`:

1. When a caller is done with the lock and wants to give it back cleanly,
   how does it prove to Redis that the key currently holds ITS lock and not
   somebody else's?
2. What happens if a caller's `ttl_ms` runs out while the caller is still
   alive and still working -- who has the lock now, and does the original
   caller have any way of knowing that happened?

Sit with those two questions before moving on to hint-2 and hint-3. Almost
every distributed-lock bug people ship in production traces back to getting
one of those two answers wrong.
