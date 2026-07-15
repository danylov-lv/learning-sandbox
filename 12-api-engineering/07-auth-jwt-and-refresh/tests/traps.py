"""Standalone + importable trap battery for 12-api-engineering task 07
(JWT auth with refresh rotation).

Fires a battery of forged/abused tokens at a running app and reports, per
trap, whether it was correctly REJECTED (401/403). None of this trusts the
app's own success/failure framing blindly -- each trap independently
decides what "correctly rejected" means for its own case (see each
function's docstring) and the summary line only counts traps that were
actually rejected.

Several traps FORGE tokens from scratch using the fixture RS256 keypair
committed in src/app.py (ACCESS_TOKEN_PRIVATE_KEY_PEM /
ACCESS_TOKEN_PUBLIC_KEY_PEM) -- this is fixture-only key material, exactly
like the module's fixture passwords; see src/app.py's module docstring.
Forged tokens are built by hand (base64url segments assembled directly),
not via `jwt.encode`, because PyJWT's own `encode()` refuses to produce an
HS256 token from a PEM-shaped key (it raises InvalidKeyError itself,
starting around PyJWT 2.10) -- a real attacker doesn't go through PyJWT to
forge a token, so hand-building is what actually exercises the server's
verification path.

Run standalone (launches the app itself on an ephemeral port, resets its
own `t07` schema first):

    uv run python tests/traps.py

Prints one line per trap and a summary, exits 0 if every trap was rejected,
1 otherwise (including the case where the battery couldn't even log in --
e.g. against the stock, unimplemented stub, which is expected to fail this
way).

`run_all_traps(client, access_token, refresh_token, user_id, other_user_id)`
is also imported directly by tests/validate.py, which reuses an
already-running app/client and the tokens from its own happy-path login
instead of logging in a second time.
"""

import base64
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

import jwt  # noqa: E402

from harness.common import build_password, pg_conn, run_async  # noqa: E402
from harness.service import run_app  # noqa: E402

from src.app import (  # noqa: E402
    ACCESS_TOKEN_ALG,
    ACCESS_TOKEN_PRIVATE_KEY_PEM,
    ACCESS_TOKEN_PUBLIC_KEY_PEM,
    ACCESS_TOKEN_TTL_SECONDS,
    app,
)

TRAP_USER_ID = 4242    # "user A" -- the battery logs in as this seeded user
OTHER_USER_ID = 4243   # "user B" -- an IDOR target; never logged into


# --------------------------------------------------------------------------
# Hand-built forgery helpers (deliberately not jwt.encode -- see docstring)
# --------------------------------------------------------------------------

def _b64url(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def _forge_none(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    return (header_b64 + b"." + payload_b64 + b".").decode()


def _forge_hs256_with_public_key(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = header_b64 + b"." + payload_b64
    sig = hmac.new(ACCESS_TOKEN_PUBLIC_KEY_PEM.encode(), signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + _b64url(sig)).decode()


def _access_payload(user_id, *, exp_delta=ACCESS_TOKEN_TTL_SECONDS):
    now = int(time.time())
    return {"sub": str(user_id), "type": "access", "iat": now, "exp": now + exp_delta}


def _genuine_signed(payload: dict) -> str:
    """A real RS256 signature from the real private key -- used for the
    expired-token trap, where the ONLY thing wrong with the token is `exp`."""
    return jwt.encode(payload, ACCESS_TOKEN_PRIVATE_KEY_PEM, algorithm=ACCESS_TOKEN_ALG)


def _rejected(resp) -> bool:
    return resp.status_code in (401, 403)


# --------------------------------------------------------------------------
# Individual traps -- each returns (rejected: bool, detail: str)
# --------------------------------------------------------------------------

async def trap_alg_none(client, user_id=TRAP_USER_ID):
    token = _forge_none(_access_payload(user_id))
    resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    return _rejected(resp), f"alg=none forged token -> HTTP {resp.status_code}"


async def trap_algorithm_confusion(client, user_id=TRAP_USER_ID):
    token = _forge_hs256_with_public_key(_access_payload(user_id))
    resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    return _rejected(resp), f"HS256-signed-with-public-key forged token -> HTTP {resp.status_code}"


async def trap_tampered_signature(client, real_access_token):
    header_b64, payload_b64, sig_b64 = real_access_token.split(".")
    flipped = ("A" if sig_b64[-1] != "A" else "B") + sig_b64[:-1]
    tampered = f"{header_b64}.{payload_b64}.{flipped}"
    resp = await client.get("/me", headers={"Authorization": f"Bearer {tampered}"})
    return _rejected(resp), f"tampered signature on a real token -> HTTP {resp.status_code}"


async def trap_absent_signature(client, real_access_token):
    header_b64, payload_b64, _sig_b64 = real_access_token.split(".")
    stripped = f"{header_b64}.{payload_b64}."
    resp = await client.get("/me", headers={"Authorization": f"Bearer {stripped}"})
    return _rejected(resp), f"absent signature on a real payload -> HTTP {resp.status_code}"


async def trap_expired_access(client, user_id=TRAP_USER_ID):
    payload = _access_payload(user_id, exp_delta=-3600)
    payload["iat"] -= 7200
    token = _genuine_signed(payload)
    resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    return _rejected(resp), f"genuinely-signed but expired access token -> HTTP {resp.status_code}"


async def trap_refresh_as_access(client, real_refresh_token):
    resp = await client.get("/me", headers={"Authorization": f"Bearer {real_refresh_token}"})
    return _rejected(resp), f"real refresh token used as access token -> HTTP {resp.status_code}"


async def trap_access_as_refresh(client, real_access_token):
    resp = await client.post("/auth/refresh", json={"refresh_token": real_access_token})
    return _rejected(resp), f"real access token used as refresh token -> HTTP {resp.status_code}"


async def trap_rotated_refresh_reuse(client, real_refresh_token):
    """Rotate once (legitimate), then replay the SPENT refresh token. A
    correct implementation must reject the replay AND kill the whole
    family: the token issued by the legitimate rotation must also stop
    working afterwards."""
    r1 = await client.post("/auth/refresh", json={"refresh_token": real_refresh_token})
    if r1.status_code != 200:
        return False, f"could not even set up the trap -- legitimate rotation failed: HTTP {r1.status_code}"
    rotated_refresh = r1.json().get("refresh_token")
    if not rotated_refresh:
        return False, "legitimate rotation response had no refresh_token -- cannot continue trap"

    r2 = await client.post("/auth/refresh", json={"refresh_token": real_refresh_token})
    replay_rejected = _rejected(r2)

    r3 = await client.post("/auth/refresh", json={"refresh_token": rotated_refresh})
    family_killed = _rejected(r3)

    detail = (
        f"replay of spent token -> HTTP {r2.status_code} "
        f"({'rejected' if replay_rejected else 'ACCEPTED'}); "
        f"then the token from the legitimate rotation -> HTTP {r3.status_code} "
        f"({'family killed' if family_killed else 'STILL VALID -- family not revoked'})"
    )
    return (replay_rejected and family_killed), detail


async def trap_authz_idor(client, real_access_token, user_id=TRAP_USER_ID, other_user_id=OTHER_USER_ID):
    """A valid token for user A, plus a spoofed identity hint aimed at user
    B. "Rejected" here means the attempt to read B's data failed -- either
    the request is denied outright, or it succeeds but still returns A's
    own identity (the spoof was silently ignored, which is the CORRECT
    behavior for an endpoint that must derive identity only from the
    token)."""
    resp = await client.get(
        "/me",
        params={"user_id": other_user_id},
        headers={"Authorization": f"Bearer {real_access_token}", "X-User-Id": str(other_user_id)},
    )
    if resp.status_code in (401, 403):
        return True, f"spoofed user_id param -> HTTP {resp.status_code} (denied outright)"
    if resp.status_code != 200:
        return False, f"spoofed user_id param -> unexpected HTTP {resp.status_code}"
    body = resp.json()
    returned_id = body.get("id")
    if returned_id == other_user_id:
        return False, f"spoofed user_id param -> HTTP 200 leaked user B's identity (id={returned_id})"
    if returned_id == user_id:
        return True, f"spoofed user_id param -> HTTP 200 but returned caller's OWN identity (id={returned_id}), spoof ignored"
    return False, f"spoofed user_id param -> HTTP 200 with unexpected id={returned_id!r}"


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def _reset_t07_schema():
    with pg_conn() as conn:
        conn.execute("DROP SCHEMA IF EXISTS t07 CASCADE")
        conn.execute("CREATE SCHEMA t07")
        conn.commit()


async def login(client, user_id=TRAP_USER_ID):
    """Log in as a seeded user via the real /auth/login endpoint. Returns
    (ok, access_token_or_None, refresh_token_or_None, detail)."""
    with pg_conn() as conn:
        row = conn.execute("SELECT email FROM shop.users WHERE id = %s", (user_id,)).fetchone()
    if row is None:
        return False, None, None, f"seeded user id {user_id} not found in shop.users"
    email = row[0]
    resp = await client.post("/auth/login", json={"email": email, "password": build_password(user_id)})
    if resp.status_code != 200:
        body = resp.text.strip().splitlines()
        tail = body[-1] if body else "(empty)"
        return False, None, None, f"POST /auth/login returned HTTP {resp.status_code}: {tail[:200]}"
    body = resp.json()
    access = body.get("access_token")
    refresh = body.get("refresh_token")
    if not access or not refresh:
        return False, None, None, f"login response missing access_token/refresh_token: {body!r}"
    return True, access, refresh, f"logged in as user {user_id} ({email})"


async def run_all_traps(client, real_access_token, real_refresh_token,
                         user_id=TRAP_USER_ID, other_user_id=OTHER_USER_ID):
    """Run every trap against `client` using genuine tokens from an
    already-completed login. Returns a list of (name, rejected, detail)."""
    results = []

    rejected, detail = await trap_alg_none(client, user_id)
    results.append(("alg=none forged token", rejected, detail))

    rejected, detail = await trap_algorithm_confusion(client, user_id)
    results.append(("HS256/RS256 algorithm confusion", rejected, detail))

    rejected, detail = await trap_tampered_signature(client, real_access_token)
    results.append(("tampered signature", rejected, detail))

    rejected, detail = await trap_absent_signature(client, real_access_token)
    results.append(("absent signature", rejected, detail))

    rejected, detail = await trap_expired_access(client, user_id)
    results.append(("expired access token", rejected, detail))

    rejected, detail = await trap_refresh_as_access(client, real_refresh_token)
    results.append(("refresh token used as access token", rejected, detail))

    rejected, detail = await trap_access_as_refresh(client, real_access_token)
    results.append(("access token used as refresh token", rejected, detail))

    rejected, detail = await trap_rotated_refresh_reuse(client, real_refresh_token)
    results.append(("rotated-then-reused refresh token", rejected, detail))

    rejected, detail = await trap_authz_idor(client, real_access_token, user_id, other_user_id)
    results.append(("cross-user authz (IDOR probe on /me)", rejected, detail))

    return results


async def _run_standalone():
    _reset_t07_schema()
    async with run_app(app) as svc:
        async with svc.client(timeout=15.0) as client:
            ok, access, refresh, detail = await login(client)
            if not ok:
                return False, [], detail
            results = await run_all_traps(client, access, refresh)
            return True, results, detail


def main():
    logged_in, results, login_detail = run_async(_run_standalone())
    if not logged_in:
        print(f"TRAP BATTERY ABORTED: could not log in -- {login_detail}")
        print("(expected against the stock, unimplemented stub)")
        sys.exit(1)

    print(f"logged in: {login_detail}")
    failures = 0
    for name, rejected, detail in results:
        status = "rejected (correct)" if rejected else "NOT REJECTED -- VULNERABLE"
        print(f"[{name}] fired -> {status}: {detail}")
        if not rejected:
            failures += 1

    total = len(results)
    if failures:
        print(f"{failures}/{total} traps NOT rejected -- VULNERABLE")
        sys.exit(1)
    print(f"ALL {total} TRAPS REJECTED")
    sys.exit(0)


if __name__ == "__main__":
    main()
