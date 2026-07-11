# Module 08 — wave-3 live verification notes

Record of the serial live-verification pass over all 8 tasks (stock stub must
fail cleanly; a reference solution must make the validator pass; the stub is
then restored byte-identical). The stack was left up from wave 1 (5 services
healthy, source at stock seed). Reference solutions were written in place,
proven, and reverted — none are committed.

## Result: every task verified

| Task | stock-fail | pass-path (reference solution) |
|------|-----------|-------------------------------|
| 01 connector-setup | NOT PASSED (register.py NotImplementedError, exit 1) | PASSED — snapshot 20000 offers + 5000 products op=r; streaming c/u/d with populated before-image |
| 02 change-event-anatomy | NOT PASSED (anatomy.py NotImplementedError) | PASSED — tally exact (r=20000 c=200 u=300 d=100); all 300 updated prices decoded exactly out of the base64 Decimal encoding |
| 03 updates-and-deletes-downstream | NOT PASSED (materialize.py NotImplementedError) | PASSED — replica.offers converged (20200 rows) after 500 ins / 1000 upd / 300 del |
| 04 schema-evolution | NOT PASSED (materialize.py NotImplementedError) | PASSED — replica converged across ADD COLUMN discount_pct (50 pre-existing + 300 new offers) |
| 05 replica-lag-and-alerting | NOT PASSED (monitor.py NotImplementedError) | PASSED — snapshot 1: lag 0, alert FALSE; snapshot 2 (under burst): consumer_lag 3300 alert TRUE, slot_lag_bytes ~1e6 |
| 06 exactly-once-materialization | NOT PASSED (final clean run hits stub) | PASSED — replica exact (20400) after two injected crashes; mart.t06_meta.applied_changes=22700 == independently drained non-tombstone count |
| 07 cdc-vs-rescraping-writeup | NOT PASSED (ANSWER.md section under 200 chars) | PASSED — all required sections filled; NOTES.md complete (validator does literal substring checks, so keywords must not wrap across a newline) |
| 08 capstone CP1 | NOT PASSED (pipeline.py NotImplementedError) | PASSED — mart==source; cap_meta.applied_changes=22700 == drained non-tombstone count |
| 08 capstone CP2 | NOT PASSED (monitor.py NotImplementedError) | PASSED — converged incl. discount_pct after two crashes + mid-stream schema change + two bursts; applied_changes=22145 exact; lag snapshot recorded |
| 08 capstone CP3 | NOT PASSED (DESIGN.md not found) | design-doc check + CP1/CP2 re-run path sound; CP3 imports and calls validate_cp2.main(), so the CP2 fix below applies to it too |

## Two problems found and fixed this session

### 1. Task 08 pipeline.py / monitor.py shipped fully implemented (not stubs)

Inherited state had `08-capstone-converge/src/pipeline.py` and `monitor.py`
already fully implemented — a prior wave implemented them and never reverted.
Their docstrings still said "TODO: implement" but the function bodies held real
code, and no `raise NotImplementedError` (unlike the other five tasks, which
all ship as clean stubs). This would have leaked a reference solution into the
committed tree, violating the "no reference solutions anywhere" rule.

Fixed: both converted to proper stubs matching the module convention
(detailed docstring contract ending in `raise NotImplementedError`, with the
given plumbing — `main`, `ensure_tables`, `_maybe_crash` — left intact). The
inherited implementations were verified correct by the CP1/CP2 pass-path runs
before being reverted.

### 2. validate_cp2.py: unreachable second-crash threshold

`08-capstone-converge/tests/validate_cp2.py` had `CRASH_2_AFTER = 20000`, which
a correct solution can never trip. The second crash run resumes after crash 1
(`S08_CRASH_AFTER=9000`) has committed ~9000 offsets; the whole CP2 corpus is
only ~22.4k messages (20000 snapshot + ~45 discount-burst + ~2400 workload +
~300 delete tombstones), so run 2 has only ~13.4k messages left, and the
per-run `processed` counter restarts at 0 — it maxes out around 13.4k < 20000,
the run catches up and exits 0, and the validator fails at the "expected a
nonzero exit from the injected crash hook" check.

This is the identical bug the task-06 author already hit and fixed
(`06-exactly-once-materialization/tests/validate.py`, `CRASH_AFTER_2` lowered
from 18000 to 10000). Fixed CP2 the same way: `CRASH_2_AFTER = 10000` (with a
comment explaining the ceiling). CP3 reuses `validate_cp2.main()` by import, so
the one-line fix covers CP3 as well.

Proven: after the fix, `validate_cp2.py` PASSED end-to-end against the verified
reference pipeline/monitor (two crashes, schema change, two bursts, monitor
snapshot, final clean run, exact convergence + applied_changes match).

## Stock state restored after verification

- All 8 `src/` stubs back to `raise NotImplementedError` (task 02 has two: the
  Decimal decoder and the tally/upsert loop).
- Task 07 `ANSWER.md` / `NOTES.md` back to their shipped templates (re-run
  confirms NOT PASSED again).
- No `DESIGN.md` in the capstone task root; no reference code anywhere in `src/`.
- Source reseeded to stock: 20000 offers, 5000 products, no `discount_pct`
  column. No connectors, replication slots, or `s08.*` data topics left behind.
- Stack left running (all 5 services healthy). `docker compose down -v` if a
  cold byte-identical stock state is needed.
