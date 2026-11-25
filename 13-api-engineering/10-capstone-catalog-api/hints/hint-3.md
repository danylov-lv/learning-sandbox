Concrete shapes for the two pieces hint-2 named, plus the smaller details
that are easy to get subtly wrong.

**Cache endpoint, all three branches:**

```
key = CACHE_PREFIX + str(category_id)
try:
    cached = redis_client.get(key)
except redis.exceptions.RedisError:
    cached = None
    redis_down = True   # remember this -- see below
else:
    redis_down = False

if cached is not None:
    return cached_value, header="HIT"

value = compute_from_postgres(category_id)   # your count/sum/avg query

if redis_down:
    return value, header="BYPASS"   # do not attempt to SET

try:
    redis_client.set(key, serialized_value, ex=CACHE_TTL_SECONDS)
except redis.exceptions.RedisError:
    pass   # value is still correct even if the write-back failed

return value, header="MISS"
```

The one bug this shape is designed to avoid: catching the exception around
`get()` but forgetting that a failed `set()` afterwards must NOT turn a
perfectly good, already-computed Postgres answer into a 500. Both Redis
calls need their own failure handling, and neither failure should ever
surface as anything other than a still-200 response with the right data.

**Refresh rotation, the exact statement:**

```sql
UPDATE t10.refresh_tokens
SET revoked = true
WHERE jti = %s AND revoked = false AND expires_at > now()
RETURNING user_id;
```

Run this with the `jti` claim extracted from the decoded refresh JWT. Zero
rows back means: wrong jti (never existed, or belongs to a token you never
issued), already rotated (this exact case is what "rotated JWTs must be
rejected" tests -- call `/auth/refresh` once successfully, then call it
AGAIN with the SAME original refresh token string; the second call must hit
this exact WHERE clause and get nothing back), or the row's own
`expires_at` has passed. All three collapse to the same response: 401. One
row back means: mint a brand-new access+refresh pair for that `user_id` --
a NEW `INSERT` for the new refresh token, a NEW `jti`, not reusing the old
row.

**Two details worth getting right without extra hand-holding:** (1) the
`sub` claim in your JWTs will come back from `jwt.decode` as whatever type
you encoded it as -- encoding it as a `str` and converting back to `int`
in `require_user`/`decode_token` avoids a JSON-number-vs-string mismatch
surprising you later. (2) `verify_password` (from `harness.common`) never
raises on a malformed stored hash, it returns `False` -- so a nonexistent
email and a wrong password can both flow through the exact same "401,
generic message" branch without you needing to special-case either one.
