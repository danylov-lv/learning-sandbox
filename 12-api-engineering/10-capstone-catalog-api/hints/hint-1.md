Five subsystems, one service. The temptation is to treat this as "build five
things," but the checkpoints are structured to fight that: CP1 wants all
five working together against a healthy stack, and CP2 wants the SAME
service to survive being attacked and degraded, not a rewrite with defenses
bolted on afterward. Build with CP2 already in mind, even while you're only
running CP1.

Concretely, that means:

- **Pagination** (`/catalog/products`) is a straight port of task 01's
  cursor endpoint, plus one more `WHERE` clause for the optional category
  filter. If you already have working cursor-pagination code from task 01,
  you understand this piece; the only new thing is composing two predicates
  in one keyset query without breaking the index-friendly shape.

- **Caching** (`/catalog/categories/{id}/summary`) starts from task 02's
  cache-aside shape, but this capstone adds a THIRD outcome beyond MISS/HIT:
  what happens when Redis itself is unreachable. Decide from the start that
  every Redis call in this handler is inside its own try/except -- don't
  write the happy-path MISS/HIT logic first and try to retrofit
  failure-handling around it later, that's where the "still returns 200 with
  correct data" requirement quietly breaks.

- **Rate limiting** (`/catalog/search`) is task 03's atomic Lua-EVAL limiter,
  applied to a genuinely new endpoint. The engineering is identical; what's
  new is that this endpoint is ALSO where the SQL injection battery lands in
  CP2 -- the limiter and the query-safety concern are two independent
  properties of the same handler, and getting one right says nothing about
  the other.

- **Auth** is the one piece with no direct predecessor task in this module.
  Read `src/app.py`'s module docstring closely before writing any JWT code
  -- it explains a subtlety (why a refresh token needs a database row, not
  just a signature check) that changes the shape of `/auth/refresh` from
  what a first instinct might produce.

Work roughly in that order -- pagination, then caching, then rate limiting,
then auth -- since each is close to self-contained and testable in
isolation before CP1 asks for all four at once. The next hint gets specific
about the two trickiest mechanisms: Redis-outage handling and refresh-token
rotation.
