# Module 17 design notes — OFF-LIMITS TO THE LEARNER BEFORE FINISHING A TASK

This directory (`.authoring/`) is committed but must not be read before you
attempt a task — see `CONVENTIONS.md`. There are no reference solutions
here (there never are, anywhere in this repo): this file documents the
grading *contract*, not answers. Read it after finishing a task, if at all.

This is the design contract for task-authoring agents building tasks
01–06 of `17-system-design`. It documents infrastructure that is already
built (`harness/`, `pyproject.toml`, `uv.lock`) and the decisions behind
it, so a task agent does not have to re-derive the harness contract.

## Why this module looks different from the rest of the repo

Every other module has a docker stack, seeded data, and code the learner
writes against a running service. Module 17 is a **writing** module —
system design at the "whiteboard interview" level, done in files instead
of on a whiteboard. There is no docker, no database, no ports. The
deliverable per task is:

1. A filled-in `DESIGN.md` — a structured design document.
2. A small, pure-Python `src/estimate.py` — a back-of-the-envelope
   capacity model over a committed `workload.json`.

Both are graded **objectively**, by structure and by number, never by a
human or an LLM reading prose for "good design sense." That is the whole
point of building this as a sandbox task instead of just journaling.

## The two-gate grading model

Every task's `tests/validate.py` runs two independent gates. Both must
pass; a task can fail either one for an unrelated reason (a fine design
doc with a broken capacity model, or vice versa), so authoring agents
should keep the two checks in the validator clearly separated and report
failures from whichever gate tripped first.

### Gate 1 — capacity model (`src/estimate.py`), graded numerically

The validator imports the learner's module via
`harness.common.import_estimate`, confirms the required functions exist
via `check_estimate_module`, then calls each function and compares its
return value against the validator's **own, independently written**
recomputation of the same formula, via `harness.common.check_close`.

**Anti-hardcode rule (load-bearing):** a validator that only checks the
committed `workload.json` can be satisfied by a learner who hardcodes the
expected numbers as constants instead of writing the formula. To close
that hole, every capacity-model check in every task **must** call each
estimate function against **at least 3 workload variants**: the committed
`workload.json` as shipped, plus at least two perturbed copies the
validator constructs in-process (e.g. `dict(workload, sites=workload["sites"]
* 3)`, or a scaled `qps`/`retention_days`/`avg_row_bytes`). A hardcoded
return value agrees with the validator's recomputation on the shipped
workload by construction, but diverges on a perturbed one — that is
precisely what catches it. Do not perturb by writing new files to disk;
build variant dicts in memory in the validator and call
`estimate.<fn>(variant)` directly.

Because both sides recompute the same formula independently, the task's
`README.md` **must pin the formula precisely** — units, rounding
direction, which overheads are included (replication factor, index
overhead, header bytes, etc.) — tightly enough that a learner's correct
arithmetic and the validator's independent implementation agree within
`check_close`'s default `rel_tol=1e-6` (relax `rel_tol` per-call, never the
spec, if a formula has an inherent rounding step — e.g. "round up to the
nearest whole shard" — and say so explicitly in the README).

### Gate 2 — design doc structure (`DESIGN.md`), graded structurally

Never graded for "is this a good design" — only for shape:

- Required `## ` sections exist (`harness.common.check_sections`), each
  with a minimum length, and none still contain a placeholder marker.
- Grounding-keyword coverage (`check_keywords`) — the doc must actually
  mention the concrete mechanisms the task is about (e.g. "sharding",
  "replica", "TTL", "backpressure") rather than staying abstract.
- Quantitative claims are present (`check_quantitative`) — a design doc
  that never writes down a number (throughput, size, latency, cost) is
  rejected even if the prose reads well.
- The hostile-review subsections (`### Q1`, `### Q2`, ... under a final
  `## Hostile Review` section) are answered, not just restated
  (`check_answers` — rejects empty, too-short, placeholder-marked, or
  verbatim-copy-of-the-question answers).

## No reference solutions anywhere

Same rule as every module, applied to this module's specific artifacts:

- `DESIGN.md` ships as an **unfilled template**: every required `## `
  heading present (so `check_sections` can discover the shape), every
  body containing a placeholder marker from
  `harness.common.PLACEHOLDER_MARKERS` (e.g. `[fill in: ...]`) instead of
  content.
- `NOTES.md` ships as the standard unfilled "What I learned / Gotchas /
  Open questions" template, same as every other module.
- `src/estimate.py` ships with every required function defined with a
  correct signature and a docstring stating its contract (inputs, units,
  output units) but a body of `raise NotImplementedError` only. The
  formula itself is never written down in the scaffold — only in the
  README's prose spec and in the validator's independent recomputation
  (which the learner never reads, since `tests/validate.py` is allowed to
  be read but should not be written as a spoiler-shaped derivation — keep
  the validator's math terse and unexplained, the README carries the
  spec).
- Hints (`hint-1.md`..`hint-3.md`) point at the relevant mechanism or
  formula shape, never at ready-made code or arithmetic.

## Module task list

- **01-price-monitoring-10k-sites** — design a system that polls ~10k
  target sites for price changes on some cadence. Capacity model: request
  rate, worker/connection pool sizing, storage for raw snapshots.
- **02-price-history-storage** — storage for years of price history with
  fast range queries. Capacity model: row/column storage footprint at
  scale, partitioning granularity, index overhead.
- **03-delivery-with-client-slas** — a scraped-data delivery pipeline that
  must meet per-client SLAs (freshness, availability). Capacity model:
  queue depth/backlog under burst, delivery latency budget.
- **04-multi-tenant-platform** — a multi-tenant scraping platform (shared
  infrastructure, isolated tenant data/quotas). Capacity model: per-tenant
  resource accounting and noisy-neighbor headroom.
- **05-outage-postmortem-redesign** — given a scripted outage narrative,
  write the postmortem and redesign the weak point. Capacity model:
  recompute the capacity assumption that the postmortem shows was wrong,
  and size the fix.
- **06-capstone-design-review** (multi-evening) — a from-scratch system
  design capstone, split into three checkpoints:
  - **CP1** — requirements gathering + capacity model (same two-gate
    shape as tasks 01–05).
  - **CP2** — architecture + explicit failure-mode analysis + a written
    10x-growth evolution plan.
  - **CP3** — the hostile-review pass, and it **re-runs CP1 and CP2's
    validators as subprocesses** (same pattern as module 16 task 07's
    CP1/CP2 re-run) so a capstone can't be "finished" by patching CP3
    while quietly regressing CP1/CP2.

## Harness contract (`harness/common.py`)

Public API is fixed — task validators across all six tasks are written
against these exact names and signatures; do not rename or change them
when building a task:

`not_passed`, `passed`, `guarded`, `_last_line`, `load_workload`,
`check_close`, `read_doc`, `parse_sections`, `parse_subsections`,
`PLACEHOLDER_MARKERS`, `check_no_placeholders`, `check_sections`,
`check_keywords`, `check_quantitative`, `check_answers`,
`check_estimate_module`, `import_estimate`.

Notable behaviors a task author should know when writing a validator:

- `parse_sections` splits on exact `## ` headings; a level-2 section's
  body runs up to the *next* `## ` heading, so it includes any nested
  `### ` subsections underneath it (including their content and any
  placeholder markers they still contain). This is intentional — a
  `## Hostile Review` section containing unfilled `### Q1`/`### Q2`
  placeholders will correctly fail `check_sections`' placeholder scan
  under the `Hostile Review` heading, not silently pass because the
  placeholder lives one level deeper.
- `check_keywords` and `check_quantitative` count **distinct** hits — a
  learner cannot pass by repeating one keyword or one number many times.
- `check_answers` rejects an answer that is a verbatim copy of the
  question line (first non-empty line of the subsection body) — a
  learner who lets the template's restated question stand in as the
  answer needs to actually add content below it.
- `check_close`'s default `rel_tol=1e-6` assumes the learner used the
  README's exact formula; if a task's formula has a legitimate rounding
  step (ceiling to whole shards/machines, etc.), the validator should
  pass a looser `rel_tol` for that specific check rather than the README
  leaving the rounding rule ambiguous.
- `import_estimate` loads `src/estimate.py` by file path (not by package
  import), so a task's `tests/validate.py` can call it as
  `import_estimate(TASK_DIR)` regardless of whether `src/` has an
  `__init__.py`.
