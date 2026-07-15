"""Validator for 12-api-engineering task 07 -- JWT auth with refresh
rotation, reuse detection, and a trap battery.

Two phases, both against ONE running instance of the learner's app:

  1. HAPPY PATH: login -> /me -> refresh -> rotated access token works ->
     rotated-away refresh token does NOT. Every claim about identity is
     checked against an INDEPENDENT oracle (shop.users queried directly via
     pg_conn, never trusting the app's own response as truth). The JWT
     header/claim shape is also sanity-checked structurally (RS256, correct
     `type`/`sub`, refresh TTL longer than access TTL -- a RELATIVE check,
     never an absolute second count) WITHOUT verifying the signature (the
     validator has no business re-implementing verification; it only
     confirms the app issued something shaped like what src/app.py's
     contract requires).

     This phase running first, and being a hard requirement before any trap
     is graded, is deliberate: a stub that 401s on EVERYTHING would
     otherwise "pass" every trap in the battery for the wrong reason (an
     app that rejects everything is not secure, it's broken). See
     .authoring/design.md's verification philosophy.

  2. TRAP BATTERY (tests/traps.py, imported and reused here against the
     SAME running app but a FRESH login/token family, so the battery's own
     rotation trap doesn't collide with the happy path's rotation above):
     every trap in tests.traps.run_all_traps must come back rejected.

`t07` (this task's owned Postgres schema) is dropped and recreated on
SETUP, not just torn down after -- so a crashed previous run never blocks a
fresh one (see .authoring/design.md's namespacing convention).

Run from this task's directory:

    uv run python tests/validate.py
"""

import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

import base64
import json

from harness.common import guarded, not_passed, passed, pg_conn, run_async  # noqa: E402
from harness.service import run_app  # noqa: E402

from src.app import app  # noqa: E402
from tests.traps import TRAP_USER_ID, login, run_all_traps  # noqa: E402


def _reset_t07_schema():
    with pg_conn() as conn:
        conn.execute("DROP SCHEMA IF EXISTS t07 CASCADE")
        conn.execute("CREATE SCHEMA t07")
        conn.commit()


def _decode_unverified(token, ctx):
    """Base64-decode a JWT's header/payload WITHOUT verifying the
    signature -- used only to sanity-check the shape of a token the app
    itself just issued over a channel we already trust (a real HTTP
    response from our own run_app instance), never to accept an untrusted
    token. Padding is re-added since JWT segments are unpadded base64url."""
    try:
        header_b64, payload_b64, _sig_b64 = token.split(".")
    except ValueError:
        not_passed(f"{ctx}: {token!r} is not a 3-segment JWT")

    def _pad(seg):
        return seg + "=" * (-len(seg) % 4)

    try:
        header = json.loads(base64.urlsafe_b64decode(_pad(header_b64)))
        payload = json.loads(base64.urlsafe_b64decode(_pad(payload_b64)))
    except Exception as e:
        not_passed(f"{ctx}: could not decode header/payload of {token!r}: {e}")
    return header, payload


async def _get_me(client, access_token):
    return await client.get("/me", headers={"Authorization": f"Bearer {access_token}"})


async def _refresh(client, refresh_token):
    return await client.post("/auth/refresh", json={"refresh_token": refresh_token})


async def _run_happy_path(client, pg):
    ok, access1, refresh1, detail = await login(client, TRAP_USER_ID)
    if not ok:
        not_passed(f"login failed: {detail}")

    oracle = pg.execute(
        "SELECT id, email, full_name, country FROM shop.users WHERE id = %s", (TRAP_USER_ID,)
    ).fetchone()
    if oracle is None:
        not_passed(f"seeded user id {TRAP_USER_ID} not found in shop.users -- corpus problem, not app problem")
    oracle_id, oracle_email, oracle_name, oracle_country = oracle

    # --- structural shape checks (no signature verification) ---
    access_header, access_payload = _decode_unverified(access1, "login access_token")
    refresh_header, refresh_payload = _decode_unverified(refresh1, "login refresh_token")

    if access_header.get("alg") != "RS256":
        not_passed(f"access token header alg={access_header.get('alg')!r}, expected 'RS256'")
    if refresh_header.get("alg") != "RS256":
        not_passed(f"refresh token header alg={refresh_header.get('alg')!r}, expected 'RS256'")
    if access_payload.get("sub") != str(TRAP_USER_ID):
        not_passed(f"access token sub={access_payload.get('sub')!r}, expected {str(TRAP_USER_ID)!r}")
    if access_payload.get("type") != "access":
        not_passed(f"access token type={access_payload.get('type')!r}, expected 'access'")
    if refresh_payload.get("type") != "refresh":
        not_passed(f"refresh token type={refresh_payload.get('type')!r}, expected 'refresh'")
    for label, payload in (("access", access_payload), ("refresh", refresh_payload)):
        exp, iat = payload.get("exp"), payload.get("iat")
        if not isinstance(exp, int) or not isinstance(iat, int) or exp <= iat:
            not_passed(f"{label} token exp/iat malformed: exp={exp!r} iat={iat!r} (need exp > iat, both ints)")
        if exp <= time.time():
            not_passed(f"{label} token is already expired at issuance (exp={exp}, now={int(time.time())})")
    access_ttl = access_payload["exp"] - access_payload["iat"]
    refresh_ttl = refresh_payload["exp"] - refresh_payload["iat"]
    if refresh_ttl <= access_ttl:
        not_passed(
            f"refresh token TTL ({refresh_ttl}s) is not longer than access token TTL ({access_ttl}s) -- "
            f"a refresh token that expires as fast as (or faster than) the access token defeats the point of refreshing"
        )

    # --- /me matches the independent oracle ---
    r = await _get_me(client, access1)
    if r.status_code != 200:
        not_passed(f"GET /me with a fresh access token returned HTTP {r.status_code}: {r.text[:200]}")
    body = r.json()
    if body.get("id") != oracle_id or body.get("email") != oracle_email or \
       body.get("full_name") != oracle_name or body.get("country") != oracle_country:
        not_passed(f"GET /me returned {body!r}, oracle expected id={oracle_id} email={oracle_email!r} full_name={oracle_name!r} country={oracle_country!r}")

    # --- refresh: rotation ---
    r = await _refresh(client, refresh1)
    if r.status_code != 200:
        not_passed(f"POST /auth/refresh with a fresh refresh token returned HTTP {r.status_code}: {r.text[:200]}")
    rotated = r.json()
    access2, refresh2 = rotated.get("access_token"), rotated.get("refresh_token")
    if not access2 or not refresh2:
        not_passed(f"POST /auth/refresh response missing access_token/refresh_token: {rotated!r}")
    # Only the REFRESH token is asserted to differ -- it must carry a fresh
    # identifier every rotation. The access token is NOT compared: two
    # access tokens minted for the same identity within the same
    # wall-clock second are legitimately byte-identical (claims are
    # second-granularity and RS256 signing is deterministic), so comparing
    # it would make this check flaky depending on timing, not correctness.
    if refresh2 == refresh1:
        not_passed("POST /auth/refresh returned the SAME refresh token that was just spent -- rotation did not actually rotate")

    # --- the NEW access token works ---
    r = await _get_me(client, access2)
    if r.status_code != 200:
        not_passed(f"GET /me with the ROTATED access token returned HTTP {r.status_code}, expected 200")
    body = r.json()
    if body.get("id") != oracle_id:
        not_passed(f"GET /me with the rotated access token returned id={body.get('id')!r}, expected {oracle_id}")

    # --- the OLD refresh token no longer works ---
    r = await _refresh(client, refresh1)
    if r.status_code not in (401, 403):
        not_passed(f"POST /auth/refresh replaying the ALREADY-ROTATED refresh token returned HTTP {r.status_code}, expected 401/403 -- rotation must invalidate the old token")

    return oracle_id


async def _check_shop_untouched(pg, before_users, before_products):
    after_users = pg.execute("SELECT count(*) FROM shop.users").fetchone()[0]
    after_products = pg.execute("SELECT count(*) FROM shop.products").fetchone()[0]
    if after_users != before_users or after_products != before_products:
        not_passed(
            f"shop row counts changed during the run (users {before_users} -> {after_users}, "
            f"products {before_products} -> {after_products}) -- shop is shared read-only, never write to it"
        )


async def _run_async_checks():
    with pg_conn() as pg:
        before_users = pg.execute("SELECT count(*) FROM shop.users").fetchone()[0]
        before_products = pg.execute("SELECT count(*) FROM shop.products").fetchone()[0]

        async with run_app(app) as svc:
            async with svc.client(timeout=15.0) as client:
                oracle_id = await _run_happy_path(client, pg)

                # Fresh, untouched login for the trap battery -- must not
                # reuse the happy path's already-rotated refresh chain.
                ok, access, refresh, detail = await login(client, oracle_id)
                if not ok:
                    not_passed(f"could not log in again for the trap battery: {detail}")
                trap_results = await run_all_traps(client, access, refresh, user_id=oracle_id)

        await _check_shop_untouched(pg, before_users, before_products)

    return trap_results


@guarded
def main():
    _reset_t07_schema()

    trap_results = run_async(_run_async_checks())

    failed = [(name, detail) for name, rejected, detail in trap_results if not rejected]
    if failed:
        lines = "; ".join(f"{name}: {detail}" for name, detail in failed)
        not_passed(f"{len(failed)}/{len(trap_results)} traps NOT rejected -- {lines}")

    passed(
        f"happy path (login -> /me -> refresh -> rotated token works -> old one doesn't) correct; "
        f"all {len(trap_results)} traps rejected ({', '.join(name for name, _, _ in trap_results)})"
    )


if __name__ == "__main__":
    main()
