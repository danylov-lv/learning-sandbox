# API engineering validator maintenance notes

Learner off-limits before attempting the tasks. These notes describe grading and fixture constraints; check live service state before running validators.

## Maintenance constraints

- Task 09 compares throughput and p95 against the machine-local baseline. Read the current validator for thresholds; correctness is checked before performance.
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
- Task 09 keeps planted-defect mechanisms in the hint tiers and grading notes; the application code exposes symptoms without annotating the answers.
- **Stub-handler style differs by task and that is intentional**: 01/04/07/10
  register a `NotImplementedError` -> clean 501 handler; 02/03/05 let it 500
  and say so in their own READMEs. Each task is internally consistent; the
  uvicorn stderr traceback under the 500 style is the server's own logging,
  not a validator leak.
