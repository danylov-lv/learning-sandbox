Concrete control flow, still no ready code.

**`POST /auth/login`**
1. Look up the row in `shop.users` by email. If missing, or
   `verify_password` on it fails, return 401 -- same status/message either
   way, don't let a caller distinguish "no such email" from "wrong
   password."
2. Mint the access token: claims exactly `sub` (the user's id, as a
   string), `type="access"`, `iat`/`exp` (now / now + your access TTL),
   signed with the fixture private key, algorithm RS256.
3. Mint the refresh token the same way but `type="refresh"`, a longer TTL,
   plus whatever extra claims you're using to carry your per-token id and
   family id (see hint-2).
4. Insert ONE new row into your `t07` table: new per-token id, a FRESH
   family id (this is a brand new login, not a rotation), the user id, not
   used, not revoked, its expiry.
5. Return both tokens.

**`POST /auth/refresh`**
1. `jwt.decode` the presented `refresh_token` with `algorithms=["RS256"]`,
   catching the broad PyJWT exception base -> 401 on any failure.
2. Check `type == "refresh"` -> 401 otherwise (this is what makes
   "access token presented as a refresh token" fail even though its
   signature is perfectly valid).
3. Pull your per-token id and family id out of the decoded claims, look up
   that row in `t07`.
   - No row found -> 401 (token id never existed, or your schema got
     reset).
   - Row `revoked` -> 401 (chain already killed).
   - Row `used` -> THIS is the reuse case: update every row sharing that
     family id to revoked, then 401.
   - Otherwise: mark this row used, insert a new row for the new token
     (same family id, new per-token id, not used, not revoked), mint a
     fresh access+refresh pair, return them.

Do the "already used" check and the "mark used + insert new row" step
inside one transaction against the same connection -- you don't want a
window where two concurrent refresh calls both see "not used yet" and both
succeed.

**`GET /me`**
1. Reject immediately (401) if the `Authorization` header is missing or
   doesn't start with `Bearer `.
2. `jwt.decode` the rest with `algorithms=["RS256"]`, same broad exception
   catch -> 401.
3. Check `type == "access"` -> 401 otherwise.
4. Look up `shop.users` by the id in `sub`. Nothing else on the request --
   not a query param, not a header, not a body field -- should ever
   influence which user id you look up. If a route parameter or query
   param FEELS like it should determine the identity here, that's the bug
   this task is testing for; delete it.
