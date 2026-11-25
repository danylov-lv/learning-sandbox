"""s12.t07 -- JWT auth with refresh rotation, reuse detection, and trap tests.

You are building the auth layer for the marketplace API: a login endpoint
that hands out a short-lived ACCESS token and a longer-lived REFRESH token,
a refresh endpoint that exchanges a refresh token for a new pair (rotating
it -- the old refresh token must stop working the instant a new one is
issued), and an identity endpoint gated on the access token. Never write to
`shop` -- this task owns Postgres schema `t07` for whatever state the
refresh-rotation scheme needs (see "Server-side state" below); `shop.users`
is read (SELECT) only, for the login lookup and the /me response.

FIXTURE CREDENTIALS -- the shared, read-only `shop.users` corpus (20,000
rows) has a real `password_hash` column. The PLAINTEXT for any seeded user
is reproducible without touching the DB: `harness.common.build_password
(user_id)` returns it (`f"pw-{id}-kupitron"`), and `harness.common.
verify_password(password, stored)` is the single source of truth for
checking a plaintext password against a stored hash -- use it (or
`build_user_password_hash`) in your /auth/login handler rather than
re-deriving the scrypt format yourself. This is fixture data for the
exercise, not a real credential scheme -- see .authoring/design.md (off
limits until you're done) for why the scrypt cost parameters are
deliberately weak.

FIXTURE KEY MATERIAL -- both token types are signed RS256 JWTs, using the
fixed keypair below. This keypair is FIXTURE-ONLY, exactly like the
fixture passwords above: it is committed and known to `tests/traps.py` on
purpose, because the trap battery needs to forge structurally-valid-but-
malicious tokens (a real private key is NEVER committed to a repo -- don't
carry this pattern into a real system). Sign with `ACCESS_TOKEN_PRIVATE_KEY_PEM`;
verify with `ACCESS_TOKEN_PUBLIC_KEY_PEM`. Both access and refresh tokens
use this same keypair and `ACCESS_TOKEN_ALG` ("RS256") -- this is what
makes the classic RS256-vs-HS256 "algorithm confusion" attack (signing a
forged token with HS256, using the PUBLIC key bytes as the HMAC secret)
meaningful to defend against: your verification call must pin
`algorithms=["RS256"]` (a list with exactly that one entry), never a
mix, and never omit the `algorithms=` argument.

REQUIRED JWT PAYLOAD CONTRACT -- tests/traps.py forges tokens from scratch
for several trap cases, so both your issuance code and its forgeries must
agree on the exact claim names below (this is the interop contract; how you
verify them is the exercise):

    {
      "sub":  "<shop.users.id, as a decimal STRING>",
      "type": "access" | "refresh",
      "iat":  <int, unix seconds>,
      "exp":  <int, unix seconds>
    }

You may add extra claims (e.g. a `jti`/`family_id` pair on the refresh
token, for your own rotation bookkeeping -- see below) -- traps.py does not
depend on anything beyond `sub`/`type`/`iat`/`exp` being present with these
exact names and semantics.

ENDPOINTS to implement:

  POST /auth/login
      Body: {"email": <str>, "password": <str>}
      200: {"access_token": <jwt>, "refresh_token": <jwt>, "token_type": "bearer"}
      401: credentials don't match a seeded shop.users row (unknown email OR
           wrong password -- don't let the response distinguish the two).
      Issues a fresh access token (TTL ACCESS_TOKEN_TTL_SECONDS, type=access)
      and a fresh refresh token (TTL REFRESH_TOKEN_TTL_SECONDS, type=refresh)
      for the authenticated user, and starts a new rotation "family" for
      that refresh token (see "Server-side state").

  POST /auth/refresh
      Body: {"refresh_token": <jwt>}
      200: {"access_token": <jwt>, "refresh_token": <jwt>, "token_type": "bearer"}
           -- a BRAND NEW pair. The refresh token just spent must stop
           working immediately (rotation): presenting it again must fail.
      401: signature invalid, wrong type (an access token presented here),
           expired, or -- the interesting case -- a refresh token that was
           ALREADY rotated away (see reuse detection below).
      REUSE DETECTION: if the presented refresh token was valid at some
      point but has already been rotated (a newer refresh token already
      exists for its family), that is a signal the token leaked -- someone
      other than the legitimate holder is replaying an old one. The correct
      response is not just "reject this one call": it must invalidate the
      ENTIRE family, so the newer, otherwise-still-valid refresh token from
      that same chain ALSO stops working from that point on.

  GET /me
      Header: Authorization: Bearer <access token>
      200: {"id": <int>, "email": <str>, "full_name": <str>, "country": <str>}
           -- looked up from shop.users by the id in the token's own `sub`
           claim. Identity comes EXCLUSIVELY from the verified token -- never
           from a query param, header, or body field a caller could set to a
           different user's id. There is no legitimate reason for this route
           to accept a client-supplied identity hint of any kind.
      401: missing/malformed Authorization header, invalid signature, wrong
           type (a refresh token presented here), or expired.

Server-side state (t07): a JWT's signature and `exp` alone cannot express
"this specific refresh token was already used" or "revoke everything issued
from this login" -- that needs a server-side record. Design your own
table(s) in schema `t07` (own it fully, create it idempotently on startup,
e.g. in a FastAPI `lifespan`) to track whatever a rotating-refresh-token
family needs: which token id is the CURRENT valid one for a family, and
whether the family has been killed by reuse detection. `hints/` walks
through one reasonable shape without handing you ready SQL.

Connecting to Postgres: `from harness.common import pg_pool, pg_conn` (see
task 01's scaffold for the same lifespan-vs-per-request tradeoff -- it
applies unchanged here).

The three route bodies below `raise NotImplementedError`, so the app
imports and launches fine -- every route just answers HTTP 501 until you
implement it (a registered handler turns the NotImplementedError into a
clean 501, so there is no traceback). Replace each body with your
implementation.
"""

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# --------------------------------------------------------------------------
# FIXTURE KEY MATERIAL -- committed on purpose, see module docstring above.
# NEVER commit a real private key; this one signs nothing but fixture data.
# --------------------------------------------------------------------------

ACCESS_TOKEN_ALG = "RS256"

ACCESS_TOKEN_PRIVATE_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCsAOM/ZrzjmNyj
tu5/pEdl0+fgEOfREdeLsfduhGvKSw89FlNni0uq2bsKy+W+jLuC+cn6BqrO0JdV
GxHrGSEIDYkO/w8eoUGoKhlIWW4KnRhjbvHbPxs8fTLHt5Inwe+U/ck0yCxPBhvq
0/l78XZhNbHDzKMNwKNUEbE6S8z3Vj4g8KP8X6+In8waiU0eNeX0wcke6gjcVMCF
Y7JhBkSTx/u9EAko+Ub2RXey19eLW1YNodZYrf3Lg0Vvw7Ow1sI5mkxQ8o+9WTZi
hp4iyLrKSfnH1v/pkpjX0nfF1klOxzhWPwTz4D/LKcnWnmL5s6VfmUCbvM/NDzAo
If/2WZidAgMBAAECggEAJusdgClCKJpcJCP+Y327lPgFYY7ZsRXhKE/onUZTsGZa
6JbOYOGlCZ+x4W/AyGSGAgz8bTkIeXq7nytcms4pCe4sGqtOE79ngIIkDdmEW1zv
2YHPMi1df4qRjJyF8r6AM/1Xgzyev/OxKel0LB32y+iPFC9Pnos9uYY2TGs90aG/
0fQ4gMP4OdAnqAES1U0DYYOcEjyoD54xEgytXBIM8a/RI7B5dmJteO3TNUBwZATp
lAGxdnxPFb3dGPS91BtzXZi7qMtRKksP77Pq1ANGRsC8Sfk6JYObepMc07oIdMob
lg0hWJOyCD0MAy/8AGH2p/IhaYU6bdEbdZFJw1w1GQKBgQDmvk3QwfJIpLU2m3bA
YjQ5gotuOIrUDhhIQx0pm+HdBXYnj7d6nGCfjtgQFt3oXM6YoTfOvlEggtx7nRjt
27pMnZS8HqjQIXSmBmpoTJgOpx64zF9ZmvyvvfXOqbl2E4J3Y0yXJ1orDntrsbq3
YbhO+Ma9gb4qXv2zQlX+SAzolQKBgQC+1J+mOeWfYY4wWGJ88uhvZ8N7BHejUs8U
OWOYVVouTiH+coUU7sktGw5UsPHmXpFoeWegUcbiXfo7MV2sFyqHpAEoFjwgyOZc
FJ+c5fIjWPVUau0fhk3nTW1fFwN5dW3X9pKtXoBHS4vHoD5Hurv95W8hpAQcbr7L
RI2soxMF6QKBgA3Ald61UH1n460HgwJgWAB9eVXuZMfStzvHVDugoMuNgcdF14el
PlUELHh5BGzO6zlJkovt5+PqKL3tVQkIKYhbc/vqT+FnvQ4QH9NrjTyCVWBqPdyX
UiwfREE2+GjDLOl0r6HqpIMgb9axVxGK73M1fJLa4ryfwLsoXvuyy6IpAoGAcH3U
kt+kXbzbXeJsRG3I2QtY76alg/Cnw6tE66K843kJjv4hN0K/8sf1PbWFE6EBpI2U
qawrSnvNq6EhL/YECyuBxwi8bzMeoH9Dy/C9OVsSW64glCnOuKAq7hgZ4zp3Aw0G
UA7aHa0J/CaZMB2C/luGlFUkW0JpVFfYEEGdUCkCgYEA2rYDnPXIPb1sVTiTYe0l
kqDUq2MeNVI277yoaCVlPgqE5KYlarjDpvO/+e3oDo38CSS5feCHZKk09AaCcXsB
5HTyphDMZwTHS8dJrjEv3ENfJA1LYEA4ioqKRYsfnXGMOrY1/g4UX98z77H3IcLY
z4w9Cb9/W71oBmf91BZusNg=
-----END PRIVATE KEY-----"""

ACCESS_TOKEN_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArADjP2a845jco7buf6RH
ZdPn4BDn0RHXi7H3boRryksPPRZTZ4tLqtm7Csvlvoy7gvnJ+gaqztCXVRsR6xkh
CA2JDv8PHqFBqCoZSFluCp0YY27x2z8bPH0yx7eSJ8HvlP3JNMgsTwYb6tP5e/F2
YTWxw8yjDcCjVBGxOkvM91Y+IPCj/F+viJ/MGolNHjXl9MHJHuoI3FTAhWOyYQZE
k8f7vRAJKPlG9kV3stfXi1tWDaHWWK39y4NFb8OzsNbCOZpMUPKPvVk2YoaeIsi6
ykn5x9b/6ZKY19J3xdZJTsc4Vj8E8+A/yynJ1p5i+bOlX5lAm7zPzQ8wKCH/9lmY
nQIDAQAB
-----END PUBLIC KEY-----"""

# Access tokens stay short-lived on purpose (traps.py's expiry trap forges
# an already-past exp; correctness here matters more than the exact number).
ACCESS_TOKEN_TTL_SECONDS = 5 * 60
REFRESH_TOKEN_TTL_SECONDS = 14 * 24 * 60 * 60


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


app = FastAPI(title="s12.t07 JWT auth with refresh rotation")


@app.exception_handler(NotImplementedError)
async def _not_implemented(request, exc):
    return JSONResponse(
        status_code=501,
        content={"detail": "endpoint not implemented yet -- implement it in src/app.py"},
    )


@app.post("/auth/login")
async def login(body: LoginRequest):
    """Verify (email, password) against shop.users, issue an access+refresh
    pair, and start a new rotation family for the refresh token.

    See the module docstring for the exact response shape, JWT claim
    contract, and the 401 case (unknown email or wrong password -- don't
    let the response distinguish which).
    """
    raise NotImplementedError


@app.post("/auth/refresh")
async def refresh(body: RefreshRequest):
    """Exchange a refresh token for a brand-new access+refresh pair, WITH
    ROTATION (the presented refresh token must stop working) and REUSE
    DETECTION (presenting an already-rotated refresh token kills its whole
    family, not just this one call). See the module docstring for the full
    contract and the 401 cases.
    """
    raise NotImplementedError


@app.get("/me")
async def me(authorization: str | None = Header(default=None)):
    """Return the caller's own identity, derived EXCLUSIVELY from a
    verified access token's `sub` claim -- never from any client-supplied
    parameter. See the module docstring for the exact response shape and
    the 401 cases (missing/malformed header, bad signature, wrong type,
    expired).
    """
    raise NotImplementedError
