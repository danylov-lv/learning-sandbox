Concrete shape, without writing the handlers for you.

**Key naming.** The scaffold fixes it: `CACHE_PREFIX + str(category_id)`,
which is `s12:t02:summary:<id>`. The `s12:t02:` prefix is the module's
namespacing rule; the `summary:` part scopes it to this endpoint so a future
endpoint's cache can't collide. One key per category is exactly right here --
the answer depends on nothing else.

**What to store, and byte-fidelity.** Store the response body you are about to
send -- a JSON string of the summary dict -- as the Redis value. On a MISS:
serialize the dict once (e.g. `json.dumps(...)`), `SETEX` that string under
the key, and return it as the body. On a HIT: `GET` the string and return it
unchanged. Because both paths return the *same stored string* as raw bytes,
the bodies are identical by construction -- which is exactly what the
validator's fidelity check wants. The trap to avoid: returning a Python dict
on the MISS (letting FastAPI serialize it its way) but the raw stored string
on the HIT -- those can differ byte-for-byte even for equal data.

**TTL.** Use the single set-with-expiry operation (redis-py's `set(key, val,
ex=CACHE_TTL_SECONDS)`, or `setex`). Setting the value and the expiry
separately risks a key that never expires if the second call is skipped.

**HIT/MISS signalling.** Return a `fastapi.Response` (or `starlette.responses.
Response`) built from the stored JSON string, `media_type="application/json"`,
with `headers={"X-Cache": "HIT"}` or `{"X-Cache": "MISS"}`. Building the
`Response` yourself is what gives you control over both the exact bytes and
the header at once -- cleaner here than declaring a `response: Response`
parameter and mutating it, because you also need to own the body.

**Invalidate.** Delete the key (`DEL`) and return 200. `DEL` on a missing key
is a no-op that still succeeds, so you don't need to branch on whether it
existed.

**Connections.** `harness.common` gives you `redis_client()` and `pg_conn()`
/ `pg_pool()`. A module-level client reused across requests is fine for this
task. (These harness clients are synchronous; calling them inside an async
handler is acceptable here -- correctness and the cache lesson are the point,
not async-driver purity, which other tasks in this module cover.)

Not spelled out on purpose: the actual handler bodies -- assemble the five
steps above yourself.
