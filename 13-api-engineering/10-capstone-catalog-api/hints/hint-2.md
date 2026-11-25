Two mechanisms are worth narrowing down before you write code: how the cache
endpoint detects and survives a dead Redis, and how refresh-token rotation
actually invalidates a used token.

**Redis outage handling.** Do NOT reach for `harness.common.redis_client()`
inside `category_summary` or `invalidate_category_cache` -- that helper
calls `sys.exit(1)` on a connection failure, which is exactly right for a
validator (fail loud, fail fast) and exactly wrong for a request handler
that's supposed to keep serving traffic. Build your own
`redis.Redis(host=..., port=redis_port(), decode_responses=True)` in this
handler (module-level or per-call, your choice) and wrap each actual
operation -- the `GET`, the `SET` -- in `try/except redis.exceptions.
RedisError`. When Redis is genuinely down (CP2 points it at a closed port),
the FIRST redis-py call you make against it raises quickly (a refused
connection doesn't hang) rather than blocking forever, so you don't need
elaborate timeout tuning to make this responsive -- catching the exception
is the whole fix. On that exception: skip straight to computing from
Postgres, skip the write-back attempt entirely (it would just fail too), and
set the response header to `BYPASS` instead of `MISS` -- that third header
value is what lets the validator prove your degradation path actually fired,
rather than the test accidentally passing because Redis happened to still
be reachable.

**Refresh-token rotation.** The JWT itself cannot tell you "this token was
already used" -- its signature and `exp` are static from the moment it's
minted. The thing that changes when a token is used is a ROW, not the
token. So: `make_refresh_token` inserts a row (`t10.refresh_tokens`) and
puts that row's `jti` in the JWT payload. `/auth/refresh` does two
completely separate checks in sequence: first, is the JWT cryptographically
valid and of type "refresh" (`decode_token`)? Second -- independently -- is
the DATABASE ROW named by its `jti` still usable? The second check and the
"mark it used" action need to be the SAME atomic statement (an `UPDATE ...
WHERE jti = %s AND revoked = false ... RETURNING user_id`), for the same
reason task 04's job creation needed one atomic `INSERT ... ON CONFLICT`
instead of a check-then-write pair: two concurrent refresh attempts with the
same token must not both succeed just because they both read `revoked =
false` before either one wrote `revoked = true`. A `SELECT` followed by a
conditional `UPDATE` has exactly that race; one `UPDATE ... RETURNING` does
not.

The next hint gets concrete about the exact SQL shapes and the exact
`X-Cache` values in each branch.
