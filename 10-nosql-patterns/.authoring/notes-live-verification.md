# Module 10 live-verification notes (final wave)

Session that took the module from "wave-1 authored, unverified" to done. Stack
(`redis/redis-stack-server:7.4.0-v3` @6310, `mongo:7` @27310, `postgres:16`
@54310) already up and healthy; `data/` already generated (SCALE=1.0,
ground-truth.json committed). All eight tasks verified live via throwaway
reference implementations written in place, run, then reverted byte-identical
(never committed) — one parallel subagent per task, the shared stack kept
collision-free by the mandated namespacing (`s10:tNN:` Redis prefixes, `tNN_`
Mongo collections, `t06` Postgres schema), so parallel verification is safe.

Every stock stub fails cleanly (single-line `NOT PASSED`, exit 1, no traceback
leak — the harness `@guarded` decorator holds across all validators). Every
task's pass-path proven with a correct reference impl (deleted after; stubs
diff-verified restored — NotImplementedError counts back to 1/2/3/5/6/11/6 for
tasks 01–06/08, ANSWER.md + DESIGN.md back to templates).

## Per-task results (reference-impl PASSED lines)

- **01 rate-limiter**: `PASSED: no over-admission (50/500 concurrent calls
  admitted, limit=50); resources isolated; window reset observed`. Ref: fixed
  window via a Lua EVAL (INCR + first-hit PEXPIRE, admit iff post-incr <= limit).
- **02 distributed-lock**: `PASSED: mutual exclusion held (120/120); wrong-owner
  release correctly rejected; fences strictly increasing`. Ref: `SET NX PX` +
  Lua compare-and-del release + INCR fencing token.
- **03 dedup-filter**: `PASSED: SET exact over 17500 unique urls; Bloom found
  17486 unique (14 false positives, 0 false negatives ...); bloom = 1.6% of
  SET`. RedisBloom `BF.*` confirmed working on the shipped image via
  `execute_command`.
- **04 redis-streams-consumer**: `PASSED: 2000/2000 events processed
  at-least-once; c1's 500 stranded pending entries reclaimed and finished by c2;
  PEL fully drained`. Ref: XREADGROUP `>` + XACK + XAUTOCLAIM reclaim.
- **05 mongodb-document-modeling**: `PASSED: correctness OK (... graded_query
  .count=2276, nested_query.count=2052); index-backed: ... IXSCAN`. Validator
  independently explains the raw filter shapes, so a correct-but-COLLSCAN answer
  cannot pass.
- **06 mongodb-vs-jsonb**: `PASSED: containment count=2276 matched on both
  sides; nested_color('black')=2052 matched on both sides; Postgres containment
  used an index (no Seq Scan), Mongo containment used IXSCAN ...; partial update
  verified`. Ref PG side: `jsonb` column + `gin (doc jsonb_path_ops)` + an
  expression index on `doc->'specs'->>'color'`. 11 stubbed functions (5 Mongo,
  6 PG); fixed a stale "ten functions" line in the README.
- **07 nosql-decision-writeup**: `PASSED: ANSWER.md filled (5 sections, each
  >=200 chars); NOTES.md completed`. Gate = 5 exact `##` headings, no `[fill in`
  markers, >= 6/8 grounding keywords, and NOTES.md >= 150 chars. Both templates
  restored.
- **08 capstone**: CP1 `count=17500 price_sum=1700991.53` == ground truth; CP2
  `survived crash+reclaim (5000 reclaimed ...) count=17500 price_sum=1700991.53
  ... XPENDING=0`; CP3 DESIGN.md 5 sections filled + CP1/CP2 re-run green. Ref:
  one doc per product_id in `t08_state`, per-batch max-`(scraped_at, event_id)`
  winner, watermark-guarded idempotent `bulk_write` upserts (reorder- and
  crash-safe). **This session also CREATED the missing `08-capstone/README.md`.**

## Bugs found this session

None. No harness/validator defects; no fixed wall-clock timeout gates a
correct-but-naive impl (CP2's only timing knobs are the structural
`MIN_IDLE_MS`/idle-sleep for XAUTOCLAIM; the 300s/600s in validate.py are outer
subprocess wrappers passed in seconds). Only cosmetic fix: README "ten" -> "eleven".

## Finalization done this session

- Created `08-capstone/README.md` (backstory / given / CP1–CP3 / criteria /
  topics; no code, no ground-truth numbers leaked).
- Filled PROGRESS.md `## 10-nosql-patterns` (8-task flat checklist, capstone
  expanded to CP1/CP2/CP3), matching module 09's format.
- Root README est-evenings 4 -> 5–6.
- CONVENTIONS.md ports (SANDBOX_10_*) were already recorded in wave-1.

## Stock state

All stubs `raise NotImplementedError`; ANSWER.md/DESIGN.md unfilled templates;
no reference solutions, no scratch dirs, no `*-local.json`, no task-dir
`__pycache__` tracked (all gitignored). Stack left running — `docker compose
down -v` for a cold stock state.
