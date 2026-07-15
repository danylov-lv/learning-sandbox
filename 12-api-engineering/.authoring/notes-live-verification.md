# Module 12 live verification (final wave)

Host: Windows 11, Git Bash, uv, Docker Compose. Stack: postgres:16 (54312) +
redis:7 (6312), both healthy. Corpus reseeded at SCALE=1.0 this session;
`data/ground-truth.json` sha256 came back
`d96d3ab6a69c499bd2515a7aaa2d666f58a5d5f18a580e3ae3e110ea4eaba305` —
byte-identical to the wave-1 value recorded in design.md, so the generator is
still deterministic across sessions and machines-state.

## Wave map

- Wave 1 (earlier session): docker-compose, pyproject/uv.lock, generate.py,
  harness/ — see notes-infra.md.
- Wave 2 (earlier session): tasks 01-06 authored. Never committed, never
  orchestrator-reviewed. Left two contamination bugs (below).
- Wave 3 (THIS session): restored 06, completed 05, authored 07/08/09/10 via
  parallel Sonnet subagents, verified everything live, wrote module docs.

## Contamination found in wave-2 output (both fixed this session)

1. **Task 04 shipped a reference solution.** `04-.../src/app.py` contained a
   fully working idempotent-insert handler (`INSERT ... ON CONFLICT
   (idempotency_key) DO NOTHING RETURNING ...`), while the actual stub sat
   beside it in an untracked `src/app.py.stub-backup`. Restored from the
   backup; backup deleted. The other four handler bodies were already stubs,
   which is why a `grep -c NotImplementedError` did not catch it — the file
   had 4 stubs AND 1 solution. Lesson: count stubs against the EXPECTED
   number per file, don't just check for nonzero.
2. **Task 06 shipped the fully SOLVED security task.** `06-.../src/app.py`
   had both fix layers already applied — parametrized SQL (`WHERE title
   ILIKE %s` with a bound param) AND a `_search_dsn()` connecting as the
   least-privilege `t06_search` role the learner is supposed to create. The
   file self-identified (`# THROWAWAY REFERENCE FIX (author verification
   only -- never committed)`) — a prior agent wrote its verification fix in
   place and never reverted. Caught by running `tests/exploit.py`, which
   reported `EXPLOIT FAILED: payload returned HTTP 500 (no leak)` — the
   security contract's "exploit must SUCCEED against stock" direction was
   broken. Restored to the vulnerable stock (f-string interpolation +
   `pg_dsn()` admin connection). Leftover `t06_search` ROLE dropped from live
   Postgres (stock must not ship with it; schema `t06` is legitimately
   created by validate.py's own `_ensure_t06_schema()` on setup, so it stays).

Both were on-disk only — nothing in module 12 had ever been committed, so git
history was never contaminated.

## Stock state verified (all 12 validators)

Every validator fails cleanly on stock: exit 1, exactly ONE `NOT PASSED:`
line, zero traceback leak into the failure output.

| validator | stock result |
|---|---|
| 01 pagination | NOT PASSED (no baseline -> run baseline.py first) |
| 02 caching | NOT PASSED (no baseline -> run baseline.py first) |
| 03 rate limiting | NOT PASSED (stub 500 on first request) |
| 04 background jobs | NOT PASSED (POST /exports 501) |
| 05 streaming | NOT PASSED (export 500, handler not implemented) |
| 06 sql injection | NOT PASSED (endpoint still injectable — exploit leaked creds) |
| 07 jwt auth | NOT PASSED (login 501) |
| 08 secrets | NOT PASSED (scaffold not implemented) |
| 09 load test | NOT PASSED (throughput 1.00x baseline, needs >= 4.5x) |
| 10 CP1/CP2/CP3 | NOT PASSED (501 / 501 / DESIGN.md placeholders) |

Note 06's stock also 500s on an ordinary quoted search (`q='Power Bank'`) —
that is not a bug, it is the injectable-SQL signature itself: an unescaped
quote breaks the interpolated statement. The fix (parametrization) is what
makes quoted input work.

## Pass paths proven live (throwaway refs, all reverted byte-identical)

Every task's pass path was reached with a reference implementation written
into a gitignored `scratch-*/` or in place, then deleted/reverted. No
reference solution survives on disk; grep-verified.

- **05**: hints/NOTES only (task body was already authored + verified).
- **06**: exploit SUCCEEDS against restored stock — leaked
  `user4242@kupitron-mail.example` + its `scrypt$1024$8$1$0f4ee9b0...` hash
  out of `shop.users` via the UNION payload. After the reference fix:
  `EXPLOIT FAILED: no credential leak` and validate.py PASSED. Both
  directions of the security contract proven.
- **07**: 9/9 traps rejected (alg=none, HS256/RS256 confusion, tampered sig,
  absent sig, expired, refresh-as-access, access-as-refresh,
  rotated-then-reused refresh, cross-user IDOR). **Negative control run**:
  narrowing `/me`'s catch from `jwt.PyJWTError` to `ExpiredSignatureError`
  flipped 4/9 traps to `NOT REJECTED -- VULNERABLE`, proving the battery has
  teeth and is not rubber-stamping.
- **08**: 6/6 planted secrets found incl. the history-only one, 0/4 decoys
  reported. Fixture determinism confirmed (identical manifests + commit shas
  across separate `uv run` invocations).
- **09**: measured stock ~35 rps / p95 ~880-930ms; full fix ~242-271 rps /
  p95 118-141ms => ~7.0-7.6x. Anti-cheat confirmed: hardcoding
  `seller_name="CHEAT"` fails on the oracle BEFORE any throughput check.
- **10**: CP1/CP2/CP3 all PASSED against the reference; CP3 shown re-running
  CP1+CP2 as subprocesses.

## Key decisions and empirics worth keeping

- **Task 09 thresholds: `MIN_RPS_RATIO = 4.5`, `MAX_P95_RATIO = 0.5`.** Chosen
  from measurement, not taste: a full three-defect fix scores ~7x on this
  machine (headroom for slower ones), while fixing ONLY the N+1 scores 4.1x /
  p95 0.68x and correctly FAILS — so a superficial one-defect fix cannot pass.
  Fix (3) (pool `max_size=1`) added little once (1)+(2) landed: the bottleneck
  had already shifted off the DB to client/loopback overhead.
- **pyjwt 2.13.0 hardens `encode()` against PEM-shaped HMAC keys**
  (`InvalidKeyError`), so the classic "sign HS256 with the RS256 public key"
  forgery cannot be built via `jwt.encode()`. Task 07's traps.py hand-builds
  the JWT (raw base64url segments + `hmac`) to exercise the real attack
  surface.
- **`jwt.exceptions.InvalidKeyError` inherits from `PyJWTError` but NOT from
  `InvalidTokenError`** — a learner catching only `InvalidTokenError` still
  500s on the confusion trap. Called out in task 07's hint-2.
- **Two access tokens minted for the same identity within one wall-clock
  second are legitimately byte-identical** (second-granularity `iat`,
  deterministic RS256). Asserting `access_token` changes after rotation is
  flaky; task 07 asserts the REFRESH token (random per-token id) changes.
- **`harness.common.redis_client()`/`pg_conn()` call `sys.exit()` on failure**
  — correct for validators, fatal inside a request handler meant to degrade
  gracefully. The capstone's cache path therefore needs its own low-level
  `redis.Redis(...)` with per-call `try/except RedisError`. Worth remembering
  before anyone reuses these helpers in app code.
- **Refresh rotation cannot be expressed by JWT signature/exp alone** — needs
  a real row + an atomic `UPDATE ... WHERE revoked=false ... RETURNING`, the
  same shape as task 04's idempotent insert.
- **`run_app_subprocess` needs `env={"PYTHONPATH": ...}`** for the child to
  import `src.app:app` — Windows subprocesses do not inherit the parent's
  `sys.path`. Also the clean way to simulate "Redis unavailable" (point the
  child at a dead port) WITHOUT stopping the shared container that other
  validators are using.
- **Windows git marks loose objects read-only** — rebuilding task 08's
  leaky-repo fixture needs an `onerror` chmod-then-retry around `rmtree`.
- **Git commits are cumulative snapshots**: a file added once persists in
  every later commit's tree, so "the secret lives in exactly one commit" is
  false. Task 08's fixture exposes `valid_commits` (every sha where the file
  is recoverable) so any reasonable scanner strategy grades fairly.
- **Task 07 commits a fixture RSA keypair** in `src/app.py`, clearly marked
  ("NEVER commit a real private key; this one signs nothing but fixture
  data") — same posture as the fixture passwords. Note the deliberate tension
  with task 08's don't-commit-secrets lesson; the labeling is what resolves it.
- **Task 09's docstrings originally enumerated all three planted defects**,
  which would have handed over the hunt. Rewritten to plain unannotated code;
  symptoms (rps/p95) live in baseline/validate output, mechanisms live in the
  hint tiers only.
- **Stub-handler style differs by task and that is intentional**: 01/04/07/10
  register a `NotImplementedError` -> clean 501 handler; 02/03/05 let it 500
  and say so in their own READMEs. Each task is internally consistent; the
  uvicorn stderr traceback under the 500 style is the server's own logging,
  not a validator leak.

## Stock state left behind

- Stack LEFT RUNNING (postgres + redis healthy), `shop` seeded at SCALE=1.0.
  `docker compose down -v` for a cold stock state.
- `data/` = committed `ground-truth.json` only.
- No scratch dirs, no `*-local.json` baselines, no `leaky-repo/`, no
  task-dir `__pycache__` tracked. `.gitignore` gained `leaky-repo/` and
  `08-secrets-management/service/secrets/`.
- Every learner src/ body is `raise NotImplementedError` except the two
  intentional non-stubs: `06-sql-injection/src/app.py` (deliberately
  vulnerable, working) and `09-load-test-and-bottleneck-hunt/src/app.py`
  (deliberately slow, working).
- `DESIGN.md` (capstone) and every `NOTES.md`/`ANSWER.md` ship unfilled.
- Pre-existing unrelated working-tree edit
  `01-sql-foundations/03-currency-normalized-revenue/src/query.sql` predates
  this session and was left untouched.
