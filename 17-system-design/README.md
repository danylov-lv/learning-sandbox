# 17 — System Design

## What this module covers

System design at the "whiteboard interview" level, applied to your world —
scraping and data-delivery systems, not generic "design Twitter" prompts.
There is no docker stack, no database, no ports here: the deliverables are
written. For each task you produce:

1. A filled-in `DESIGN.md` — a structured design document (components,
   data flow, bottlenecks, growth plan).
2. A small `src/estimate.py` — a back-of-the-envelope capacity model: a
   handful of pure-Python functions that turn a given `workload.json` into
   numbers (storage footprint, request rate, worker counts, cost).

This module runs **ongoing, in parallel with the other modules** — pick up
a task on an evening when you'd rather think and write than run code.

## The two-gate grading model

Each task's validator checks two independent things. Both must pass.

**Gate 1 — the capacity model is checked numerically.** The validator
imports your `src/estimate.py`, calls each required function, and compares
the result against its own independent recomputation of the same formula —
not just on the committed `workload.json`, but on several perturbed
variants of it (different site counts, different retention windows, and so
on). This means the formula has to actually be a formula: hardcoding the
numbers that happen to work for the shipped `workload.json` will pass on
that file and fail the moment the validator perturbs it. The task's README
states the formula precisely enough (units, rounding, what overhead is
included) that your arithmetic and the validator's should agree closely.

**Gate 2 — the design doc is checked structurally.** Never for "is this a
good design," which is not machine-checkable — only for shape:

- Every required `## ` section is present and long enough.
- No leftover `[fill in ...]` placeholders anywhere.
- The doc actually names the concrete mechanisms the task is about
  (grounding-keyword coverage), not just abstractions.
- The doc makes quantitative claims — numbers, rates, sizes, percentages —
  not just prose.
- The final `## Hostile Review` section's `### Q1`, `### Q2`, ... questions
  are genuinely answered, not left as the restated question or a
  one-line placeholder.

A validator prints exactly one line and exits: `PASSED` on success, or
`NOT PASSED: <reason>` naming what's missing or wrong. No raw tracebacks.

## How to run a validator

Validators are run **from the module root**, always:

```bash
cd 17-system-design
uv run python 01-price-monitoring-10k-sites/tests/validate.py
```

Run `uv sync` once first if you haven't already.

## How to work with a design exercise

1. **Write `DESIGN.md` first.** Fill in every section before touching
   code — requirements, components, data flow, bottlenecks, the 10x growth
   story. This is where the actual design thinking happens.
2. **Answer the hostile-review questions in `DESIGN.md`'s final section.**
   These are deliberately the questions an interviewer or a skeptical
   colleague would ask to find the weak point in your design. Answer them
   honestly — a good answer sometimes means revising an earlier section
   once you notice the gap.
3. **Then build the capacity model** in `src/estimate.py`. By this point
   the design's shape is settled, and the estimate functions are just
   arithmetic over `workload.json` per the formula the task's README pins
   down.

## Tasks

| # | Task | Evenings |
|---|------|:---:|
| 01 | price-monitoring-10k-sites | 1 |
| 02 | price-history-storage | 1 |
| 03 | delivery-with-client-slas | 1 |
| 04 | multi-tenant-platform | 1 |
| 05 | outage-postmortem-redesign | 1 |
| 06 | capstone-design-review | 1–2 |

Total: 5–6 evenings.

- **01** — design a system that polls roughly 10,000 target sites for
  price changes on some cadence, and size it.
- **02** — design storage for years of price history with fast range
  queries, and size the footprint.
- **03** — design a scraped-data delivery pipeline that has to meet
  per-client SLAs, and size the backlog/latency budget.
- **04** — design a multi-tenant scraping platform with isolated tenant
  data and quotas, and size per-tenant resource accounting.
- **05** — given a scripted outage narrative, write the postmortem and
  redesign the weak point, resizing the capacity assumption that broke.
- **06** (capstone, multi-evening) — a from-scratch design review in three
  checkpoints: **CP1** requirements + capacity model, **CP2** architecture
  + failure modes + a 10x-growth plan, **CP3** the hostile review, which
  also re-runs CP1 and CP2's validators to make sure they still pass.

## `.authoring/` is off-limits until after a task

`.authoring/design.md` documents the grading contract for this module's
task-authoring work. It is not a solution file — there are no reference
solutions anywhere in this repo — but read it after finishing a task, if
at all, same rule as every other module.
