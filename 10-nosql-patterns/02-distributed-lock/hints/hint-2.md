For question 1 from hint-1: `release()` must be an atomic compare-and-delete
-- "delete this key, but only if it still holds MY token" -- executed as a
single operation on Redis's side.

Why "single operation" matters: imagine instead you write it as two separate
client calls, `GET` then `DEL`. Even if you check the `GET`'s result in
Python before deciding to call `DEL`, there is a real gap in wall-clock time
between those two round trips -- however small. Nothing stops the following
from happening inside that gap: your lease's TTL finishes expiring (maybe it
was already almost expired when you called `GET`), a completely different
worker calls `acquire()` and legitimately gets the lock, and THEN your `DEL`
runs. Your `DEL` doesn't know any of that happened. It just deletes whatever
is sitting in the key right now -- which is the other worker's lock, not
yours. Your Python-level `if got_value == my_token` check already passed
before any of that happened, so there's no way to catch it after the fact
from the client side.

The fix is to move the check AND the delete inside Redis itself, as one
script, so nothing else can execute in between them (Redis executes each
`EVAL` to completion before processing any other command). Look into
`redis-py`'s `Script`/`register_script` or plain `client.eval(...)`. The
script itself needs exactly two Redis commands and one conditional: read the
key, compare it to the token you were given as an argument, and delete-or-not
based on that comparison, returning something the Python side can turn into
`True`/`False`. Redis Lua scripts take two argument lists -- `KEYS` and
`ARGV` -- make sure you're passing the lock key as a `KEYS` entry and the
token as an `ARGV` entry (that distinction matters for Redis Cluster
routing, and it's the conventional way to write scripts even outside
cluster mode).
