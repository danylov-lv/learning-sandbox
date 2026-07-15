# 07 -- Auth: JWT with refresh, common pitfalls as trap tests

## Backstory

Every marketplace endpoint so far has been open to the world -- fine for a
public catalog, not fine once orders and account data enter the picture.
Product wants "log in, then everything else needs a valid session," and
someone on the team just read a blog post about JWTs and wants to ship
them today. You've seen enough real incident writeups to know that "add
JWT auth" is where a surprising number of production breaches start: `alg:
none` tokens nobody meant to accept, a refresh flow that lets one stolen
token be used forever, an endpoint that trusts whatever id a client claims
to be instead of the one in the token it actually presented. Shipping the
happy path is the easy 20%. This task is about the other 80%: a battery of
forged and abused tokens that a correct implementation must reject, every
single time.

## What's given

- `src/app.py` -- a real FastAPI `app` with the three routes defined but
  their bodies `raise NotImplementedError`. The app imports and launches
  fine; every route just answers HTTP 501 until you implement it. The
  module docstring is the full contract: exact request/response shapes,
  the required JWT claim names (`sub`/`type`/`iat`/`exp`), and a FIXTURE
  RS256 keypair you must sign and verify with -- committed on purpose, so
  the trap battery below can forge tokens that share your app's exact
  signing scheme.
- The shared, read-only `shop.users` corpus (20,000 rows, real
  `password_hash` column) and `harness.common.verify_password` -- the
  single source of truth for checking a login password against a stored
  hash. `harness.common.build_password(user_id)` gives you the plaintext
  for any seeded user without touching the DB, for your own manual
  testing.
- The module harness (`harness/common.py`, `harness/service.py`) with the
  usual Postgres helpers and ephemeral-port app launcher.
- `tests/traps.py` -- a standalone, runnable battery of forged and abused
  tokens (`uv run python tests/traps.py`, after you've implemented the
  app). Run it directly to see, one line per trap, whether your
  implementation rejected it.
- `tests/validate.py` -- the full check: happy path first, then the same
  trap battery, asserted.

## What's required

Implement all three endpoints in `src/app.py` (see its module docstring
for the byte-exact contract):

- `POST /auth/login` -- verify credentials against `shop.users`, issue a
  short-lived **access token** and a longer-lived **refresh token**, both
  RS256 JWTs signed with the fixture private key.
- `POST /auth/refresh` -- exchange a refresh token for a new access+refresh
  pair. Two properties are both required, not optional extras:
  - **Rotation**: the refresh token just spent must stop working
    immediately.
  - **Reuse detection**: if a refresh token that was ALREADY rotated away
    gets presented again, that's a signal of a stolen/leaked token -- the
    correct response revokes the entire chain it came from, not just this
    one call. A newer, otherwise-still-valid refresh token from that same
    chain must also stop working once this happens.
- `GET /me` -- return the caller's own identity (from `shop.users`),
  derived exclusively from a verified access token's claims. Never accept
  a client-supplied identity hint from anywhere else.

This needs server-side state (a JWT's signature alone can't express "this
token was already used") -- own it in Postgres schema `t07`, entirely your
own design. Never write to `shop`.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/traps.py       # after implementing: every trap line says "rejected"
uv run python tests/validate.py
```

`tests/validate.py` launches your app on an ephemeral port and checks, in
order:

1. The full happy path: login succeeds and matches `shop.users` via an
   independent query (never trusting your app's own response as truth);
   the issued tokens are structurally sane RS256 JWTs with the required
   claims; `/me` returns the right identity; `/auth/refresh` rotates
   correctly; the newly-rotated access token works; the just-spent refresh
   token does not.
2. Every trap in `tests/traps.py` -- forged/abused tokens covering `alg:
   none`, RS256/HS256 algorithm confusion, tampered and absent signatures,
   an expired-but-genuinely-signed access token, a refresh token presented
   as an access token and vice versa, a rotated-then-reused refresh token
   (and confirming the WHOLE chain dies, not just the replayed call), and
   a cross-user authorization probe on `/me`.

The happy path is checked FIRST and must pass before any trap is graded --
an implementation that just rejects everything is not "secure," it's
broken, and this ordering makes sure that can't accidentally pass.

Prints `PASSED: ...` with the observed counts, or `NOT PASSED: <reason>`
and exits 1.

## Estimated evenings

1-2

## Topics to read up on

- JWT structure (header/payload/signature) and what the signature actually
  protects (integrity, not confidentiality -- the payload is base64, not
  encrypted)
- Why `alg: none` exists in the spec at all, and why a verifier must pin
  its accepted algorithm(s) rather than trust the token's own `alg` header
- RS256 vs HS256, and the classic "algorithm confusion" attack (signing
  with HS256 using an RS256 public key as the HMAC secret) -- and why
  pinning `algorithms=[...]` to a single value defeats it
- Access token vs refresh token: why you want one short-lived and stateless
  and the other longer-lived and revocable, and why that split needs
  server-side state for the refresh side
- Refresh token rotation and reuse detection ("token family" revocation) --
  what a stolen-and-replayed refresh token looks like from the server's
  side, and why killing the whole chain (not just the replayed token)
  matters
- Confused deputy / IDOR: why "which user's data do I return" must come
  from the verified token, never from a client-supplied parameter
- Broad vs narrow exception handling around a JWT library's own exception
  hierarchy -- what happens to a caller-facing endpoint when you catch too
  narrowly

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API
contract, the `shop` schema, the fixture-password rule, and the
verification philosophy behind every task in this module -- spoilers.
Don't read it before finishing this task.
