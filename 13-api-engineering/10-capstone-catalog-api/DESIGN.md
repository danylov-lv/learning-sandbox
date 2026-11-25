# Capstone Design Memo -- Hardened Catalog API

Fill in each section with your own analysis, grounded in what you actually
built and observed across CP1 and CP2 of this capstone, and across tasks
01-06 of this module (pagination, caching, rate limiting, background jobs,
streaming, SQL injection).

## Cursor pagination at catalog scale

(fill in -- explain exactly how `/catalog/products` avoids ever asking
Postgres to skip rows, including once the optional `category_id` filter is
combined with the keyset predicate. What does `next_cursor` actually encode,
and why is that enough state to resume a sweep with no server-side session?
Cite the exact count and id-checksum CP1's full sweep reported for your
implementation, and say what would have to be true of your query for those
two numbers to match by coincidence rather than by correctness)

## Cache correctness: TTL, invalidation, and concurrent reads

(fill in -- walk through all three `X-Cache` outcomes your implementation
produces and exactly what triggers each one, especially `BYPASS`. What does
your code do differently on a `GET` failure versus a `SET` failure against
Redis, and why does a failed write-back never turn into an error response?
Describe what happened when CP2 fired a burst of concurrent readers at a
freshly-invalidated key -- did every response match the oracle, and what in
your implementation makes that true rather than accidental? What would
"thundering herd" mean for this specific endpoint, and does your
implementation solve it or merely tolerate it)

## Rate limiting and quotas under concurrency

(fill in -- name the algorithm you used and why, same as task 03's NOTES.md
would ask. What is the exact atomic unit your Redis calls perform, and why
does splitting it into two round trips break the "exactly RATE_LIMIT
admitted" guarantee under a concurrent burst? Cite the admitted counts CP1
and CP2 actually observed for your implementation against RATE_LIMIT, and
explain why a rate-rejected request costs nothing against the longer-window
quota in your implementation specifically -- not just in general)

## JWT auth: issuance, verification, and rotation

(fill in -- explain precisely why a refresh token needs a database row when
an access token does not, in terms of what "rotated JWTs must be rejected"
actually requires that a signature+expiry check alone cannot provide. Walk
through the exact atomic statement your `/auth/refresh` uses to detect reuse,
and what happens, concretely, when CP2 replays an already-rotated refresh
token against your implementation. What distinguishes your handling of a
forged token from an expired one from a malformed one -- do they fail at the
same place in your code, or different places, and does that matter for
correctness here)

## SQL injection defense

(fill in -- describe the exact query shape `/catalog/search` uses and where
`q` sits relative to the SQL text at the moment the query executes. What,
concretely, would CP2's UNION-based payload have had to look like to leak
`shop.users` data against a vulnerable version of this endpoint, and why
does your parametrized version treat that same payload as inert? Contrast
this with task 06's break-and-fix: what's different about writing this
endpoint correctly from the start versus retrofitting a fix onto a
string-interpolated query)

## Redis as an optional dependency, and what's still missing

(fill in -- state plainly which of this capstone's Redis-backed features are
required to degrade gracefully and which are not, and why that split is
defensible for a real service, not just a grading shortcut. What did CP2's
dead-Redis drill actually prove about your `/catalog/categories/{id}/summary`
endpoint, concretely -- what would have happened to a version of your code
that called `harness.common.redis_client()` inside the request handler
instead of building its own client? Beyond what CP1/CP2 test, what else in
this service would need to change for a real production deployment --
connection pooling, structured logging, secrets management for `JWT_SECRET`,
observability into cache hit rate or rate-limiter rejection rate, or
anything else you'd want before this went in front of real traffic)
