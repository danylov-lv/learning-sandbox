# Live verification notes (module 17)

Spoilers. Read after finishing the module, not before.

## What was verified

All nine validator entry points were run from the module root against the
committed stock state:

```
01/tests/validate.py  02/tests/validate.py  03/tests/validate.py
04/tests/validate.py  05/tests/validate.py
06/tests/validate_cp1.py  validate_cp2.py  validate_cp3.py  validate.py
```

Each prints exactly one `NOT PASSED:` line, exits 1, and leaks zero
traceback lines. Every task's pass path was proven live by its author with
a throwaway reference (implemented `estimate.py` plus filled documents)
that was reverted byte-identical afterwards — no reference solution is
committed anywhere.

Anti-hardcode was proven per task: an `estimate.py` returning the correct
constants for the shipped `workload.json` fails on the first perturbed
variant. The capstone additionally proved that CP3 re-runs CP1 and CP2 as
subprocesses (breaking CP1's deliverable makes CP3 fail, naming
`validate_cp1.py`), and that an ADR listing only one rejected alternative
fails CP2.

## Two bugs found in `harness/common.py` and fixed

Both were in `check_answers`, the gate that decides whether a hostile-review
question was actually answered. Three of the six task authors hit the first
one independently and worked around it locally by raising `min_chars`; the
fix below makes the harness itself correct, and every validator now passes
`questions_path`.

1. **Verbatim-copy detection only compared the body against its own first
   physical line.** A question wrapped across several lines never equals its
   first line, so pasting the question as the answer slipped through
   whenever the question text alone cleared `min_chars`. Fixed by comparing
   against the real question source: `check_answers(..., questions_path=...)`
   whitespace-normalizes both sides and subtracts matching runs of >= 40
   characters (via `difflib.SequenceMatcher`), so re-wrapping a copied
   question does not disguise it. What is left must clear
   `min_original_chars` (default 120).

2. **The old heuristic false-failed a legitimate single-paragraph answer.**
   `stripped == lines[0]` is true for any one-line body, so a task whose
   template does not restate the question (task 02) would have rejected a
   correct answer written as one paragraph. That heuristic now only runs as
   a fallback when `questions_path` is not supplied.

Hardening: `_original_char_count` de-duplicates repeated sentences first.
Without it, padding a copied question with the same filler sentence N times
reads as N sentences of original work and clears the threshold. Verified in
both directions across all six tasks — a question copied and padded to beat
`min_chars` is rejected in every task, and a genuine answer built on each
task's real `DESIGN.md` template is accepted in every task.

The capstone's aggregate `tests/validate.py` was also collapsed from a
two-line failure (its own line plus the child's) to the single-line
convention.

## Conventions worth keeping if this module is extended

- Question formats differ per task (`**Q1.**`, `## Q1`, `### Q1`, `1.`).
  That is fine — `check_answers` keys off the `### Qn` headings in
  `DESIGN.md`, not off the questions file's own formatting.
- `min_chars` per task is calibrated against that task's own question
  lengths; `min_original_chars` is what actually enforces original content.
- Timing is never gated anywhere in this module — there is nothing to time.
