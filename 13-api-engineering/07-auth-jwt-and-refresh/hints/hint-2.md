**Verification mechanics.** `jwt.decode(token, key, algorithms=[...])`
takes `algorithms` as a LIST on purpose -- PyJWT will accept a token signed
with ANY algorithm named in that list. A verifier that passes
`algorithms=["RS256", "HS256"]` "just to be safe" (or copies an example
that does) has quietly reopened the algorithm-confusion door, no matter how
careful the rest of the code is. Pass a list with exactly the one algorithm
you actually sign with. Separately: `jwt.decode` raises different exception
subclasses for different failures (expired, bad signature, disallowed
algorithm, malformed key, ...). All of them share a common base --
`jwt.exceptions.PyJWTError` (also importable off the top-level `jwt`
module). Catching a narrower subclass (say, only
`jwt.ExpiredSignatureError`) means every OTHER failure mode -- a garbage
token, a wrong-algorithm token -- falls through uncaught and becomes an
unhandled exception in your route, which FastAPI turns into an HTTP 500
with a stack trace, not a clean 401. Catch the broad base.

**Refresh-token state, one reasonable shape.** You need to answer two
questions on every `/auth/refresh` call: "is this specific refresh token
the CURRENT valid one for whatever chain it belongs to?" and, if not,
"has this chain already been flagged as compromised?" That's naturally two
booleans (something like "already used" and "chain revoked") plus two
identifiers: one per-token-issuance id (unique per token you ever mint) and
one per-LOGIN id shared by every token descended from that login (the
"family"). A table keyed by the per-token id, with a family id column, an
issued/used/revoked set of flags, and an expiry, is enough to answer both
questions with one lookup. On a successful, non-reused refresh: mark the
old row used, insert a new row with a NEW per-token id but the SAME family
id. On a reused (already-used) row: instead of just rejecting, update
EVERY row sharing that family id to revoked -- that's what makes the
newer, otherwise-still-good refresh token also stop working afterwards.

**The claim contract matters for interop, not just correctness.** Your
access and refresh tokens both need a `type` claim (`"access"` vs
`"refresh"`) checked explicitly wherever you decode them -- not inferred
from which table a lookup happened to hit, not skipped because "well it's
a valid signature." A valid signature only proves WHO signed it, never
WHAT it was for.

The next hint walks through the three endpoints' control flow concretely.
