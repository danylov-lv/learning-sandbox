# Task 08 (profiling-py-spy) -- spoilers

Culprit function (learner-invisible in `08-profiling-py-spy/src/app.py`,
recorded here only): **`compute_signature(evt)`**. It's a plain sync
function, no `await`, called inline from `process_one()` on every record's
hot path (`signature = compute_signature(evt)`, no `to_thread`/executor
wrapping in the shipped state). Its iteration count is calibrated at import
time via `_calibrate_iters(target_seconds=0.008)` -- the same technique as
task 01's `_calibrate_parse_iters` -- so it burns roughly 8ms of real CPU
per call on whatever machine runs it, machine-independent in wall-clock
terms even though the raw iteration count varies.

Decoy helpers in the same pipeline, all intentionally cheap so they don't
also trip the heartbeat check: `_parse_payload` (json.loads on a short
string), `_checksum_header` (a tiny 16-byte loop, capped at 0xFFFF -- looks
structurally like `compute_signature` but does ~1/1000th the work),
`_validate_event`, `_enrich_event`, `_serialize_event` (json.dumps). The
two `async def _simulate_*` functions are pure `asyncio.sleep` and never
touch the CPU.

The intended fix is a single call-site change in `process_one`:

```python
signature = await asyncio.to_thread(compute_signature, evt)
```

(`loop.run_in_executor(None, compute_signature, evt)` is an equally valid
fix and is accepted implicitly since the validator only checks behavior,
not the diff.)

## ANSWER.md gate (`tests/validate.py`)

- Placeholder marker `"(answer here)"` (case-insensitive) must be gone from
  all three sections.
- Stripped prose (HTML comments and `#`-heading lines removed) must be
  >= 200 chars.
- Must contain `"compute_signature"` or `"compute signature"`
  (case-insensitive substring) -- the accepted culprit spellings.
- Must contain >= 3 of: `py-spy, pyspy, flamegraph, flame graph, event
  loop, gil, to_thread, run_in_executor, thread pool, blocking, dump`
  (case-insensitive substring, counted as distinct keywords hit, not
  occurrences).

## Behavioral gate calibration

`N_VALIDATE = 40` records, `CONCURRENCY = 1`, `FETCH_LATENCY =
PERSIST_LATENCY = 0.005`, `HEARTBEAT_INTERVAL = 0.01` (all in
`tests/validate.py`, independent of `src/app.py`'s own CLI defaults of
2500 records / concurrency 12 / 0.01s latencies -- the CLI defaults are
tuned for "stay alive long enough to attach py-spy" (~20s+), the
validator's for "fast, deterministic signal" (~1.9s either way)).

**`CONCURRENCY` started at 8** (matching the CLI's worker-pool feel) but
empirical probing showed this breaks the discrimination the check depends
on: `asyncio.to_thread` still contends for the GIL against every other
concurrently-busy worker thread doing the same CPU-bound loop, so at
concurrency=8 even a *correctly offloaded* `compute_signature` only gets
the loop thread's fair share of GIL time (~1/(concurrency+1) as a rough
model), tanking the fixed run's heartbeat fraction down to ~0.13-0.21 --
barely above the broken run's ~0.13 at the same concurrency. The two
states become statistically indistinguishable as concurrency rises. Swept
concurrency 1/2/3/4/5/6/8 for both states (`n=60`, 3-4 reps each); fraction
(ticks / (elapsed/HEARTBEAT_INTERVAL)) summary:

| concurrency | broken frac | fixed frac | gap |
|---|---|---|---|
| 1 | ~0.42-0.43 | ~0.63-0.64 | ~21pt, very stable |
| 2 | ~0.41-0.43 | ~0.53-0.62 | ~10-19pt, noisier |
| 3 | -- | ~0.41 | fixed already collapsing toward broken |
| 4 | ~0.25 | ~0.34 | |
| 8 | ~0.13 | ~0.13-0.21 | effectively gone |

Settled on `CONCURRENCY = 1`, `N_VALIDATE = 40` -- broken consistently
~0.42-0.43, fixed consistently ~0.63-0.64 across many repeated runs
(near-zero variance observed), elapsed ~1.86-1.89s for both states (offload
doesn't change wall time at concurrency=1, only which thread pays for it).
Against the `0.5 * expected_unblocked_ticks` threshold (same formula as
task 01): broken lands at ticks=~80 vs. min_ticks=~92 (fails by ~13,
comfortably under); fixed lands at ticks=~119 vs. the same ~92 floor
(passes by ~26, comfortably over). This is a deliberate, documented
departure from the "realistic worker-pool concurrency" instinct -- the
in-code comment above `CONCURRENCY` in `tests/validate.py` explains the
same reasoning inline for anyone re-tuning this later.

## Verification run (this session)

- Stock (broken app.py + unfilled ANSWER.md):
  `NOT PASSED: event loop stalled while run_workload() processed 40
  records: heartbeat ticked 80 time(s) in 1.853s (expected at least 92,
  ~185 if the loop were never blocked) -- ...` -- clean, exit 1, no
  traceback. Confirms the behavioral gate is the first thing to fail (the
  ANSWER.md gate is never reached because the heartbeat check runs first in
  `main()`).
- Pass-path (scratch-patched app.py with `signature = await
  asyncio.to_thread(compute_signature, evt)` at the one call site in
  `process_one`, + filled ANSWER.md naming `compute_signature`, mentioning
  py-spy/dump/flamegraph/event loop/to_thread/GIL): `PASSED: 40 records
  processed; heartbeat ticks=119 in 1.868s; ANSWER.md OK`, exit 0.
- py-spy sanity check (separate from the validator, which never invokes
  py-spy): **py-spy attached cleanly on this Windows host, no elevation
  needed.** `py-spy dump --pid <pid>` against the live (broken) process
  caught `compute_signature (app.py:109)` directly under `process_one` at
  the top of the MainThread stack (`active+gil`) on 3/3 consecutive dumps.
  `py-spy record -o profile.svg --pid <pid> --duration 6` wrote a valid SVG
  containing the string `compute_signature`. First `py-spy record` attempt
  against a process that had already exited (duration budget ran out
  mid-command) failed with `Failed to open process ... os error 87` --
  expected/unrelated to privilege, just a "process is gone" race; a second
  attempt against a freshly-started, still-running process worked
  immediately. No privilege caveat was actually hit on this host, but the
  README/hints keep the elevated-shell guidance since py-spy's Windows
  attach behavior is known to vary by host/AV config.
- Reverted `src/app.py` to the broken (shipped) state and `ANSWER.md` to
  the unfilled template after verifying the pass-path; deleted `scratch/`
  and the `profile.svg` it contained. Killed the background `src/app.py`
  processes started for the py-spy sanity check (both had already exited
  on their own by the time cleanup ran).
