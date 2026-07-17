# 07 -- Capstone: Data Quality Platform

## Backstory

Every task in this module taught you one piece of "scraping at scale" in
isolation: staying polite against a hostile target, catching malformed
records before they poison downstream data, detecting what actually
changed instead of re-fetching everything, surviving a page whose markup
shape depends on which product you're looking at, spending render budget
only where it buys you something, and watching all of it happen live. A
real scraping operation needs every one of those at once, in one pipeline,
because the target doesn't ask which lesson you're working on this week --
it enforces its rate limit, serves whichever markup version it feels like,
and plants the same six defect shapes regardless of what you're focused on.

This capstone is that pipeline: one `run_pipeline` entrypoint that crawls
the real catalog politely, extracts every field resiliently across all 4
markup encodings, routes clean vs. quarantined records through a real
data-quality gate, spends the expensive render step only on products that
actually need it, detects day-over-day change past the volatile nonce, and
reports Prometheus metrics the whole way through. It is graded in three
checkpoints: steady state first (CP1), then chaos and change detection
(CP2), then a design memo proving you can explain what you built and that
it still holds (CP3).

## What's given

- `src/pipeline.py` -- the core entrypoint, `run_pipeline(client_id,
  day=0, chaos=False, workdir=None)`, plus the five functions it's built
  from (`discover_product_ids`, `fetch_product_html`, `extract_fields`,
  `fetch_product_detail`, `quality_check`). Every function `raise
  NotImplementedError` with a docstring spelling out its exact contract --
  read `pipeline.py`'s module docstring first, it explains how the five
  pieces compose into the one entrypoint the validators call.
- `src/changedetect.py` -- `fingerprint(payload)`, `build_fingerprint_index
  (day, client_id, product_ids=None, chaos=False)`, and `changed_between
  (day_prev, day_curr, client_id, product_ids=None, chaos=False)`, built on
  top of `pipeline.py`'s own fetch/extract functions rather than a separate
  fetch layer.
- `src/metrics.py` -- the same seven `prometheus_client` metric families
  task 06 built (`spider_pages_fetched_total{strategy}`,
  `spider_records_quarantined_total{reason}`, `spider_fetch_errors_total
  {reason}`, `spider_fetch_latency_seconds`, `spider_field_completeness
  {field}`, `spider_banned`, `spider_honeypot_hits_total`), `None`
  placeholders plus `build_registry()` and `record_*`/`set_*` helpers, all
  stubbed. Unlike task 06, nothing here needs to bind an HTTP port --
  `tests/validate_cp1.py` reads the registry in-process.
- The target site, already running via the module's `docker-compose.yml`
  at `http://localhost:8313` (`harness.common.target_base_url()`), and
  `harness/common.py`'s `target_base_url()`, `get_client_state`,
  `reset_client`, `load_catalog`, `load_ground_truth`, `load_target_spec`.
  You write your own fetch layer, same as every task in this module --
  nothing in `harness/` parses HTML, paces requests, or avoids honeypots
  for you.
- `DESIGN.md` -- an unfilled template with the seven sections CP3 checks.
- `hints/` -- three files, a nudge to something close to pseudocode.
- Three checkpoint validators: `tests/validate_cp1.py`, `validate_cp2.py`,
  `validate_cp3.py`.

## What's required

Implement `src/pipeline.py`, `src/changedetect.py`, and `src/metrics.py`.
The work is graded in three checkpoints.

### CP1 -- steady state, day 0 (`validate_cp1.py`)

**Build:** `run_pipeline(client_id, day=0)` against the healthy target --
discover every real product id (task 01's concept), extract all 7
HTML-visible fields with a fallback chain across all 4 markup versions
(task 04), gate clean vs. quarantine against the 6 planted defect shapes
(task 02), apply the budget router so only `review_count > 0` products pay
the render cost (task 05), and instrument every fetch/quarantine/
completeness event through `src/metrics.py` (task 06).

**Checked:** the discovered id set is EXACTLY the real product ids (no
honeypots, no duplicates); the client ends `banned=False`,
`honeypot_hits=0`, `header_rejections=0`, a small `rate_limit_violations`;
the quarantine sink is EXACTLY ground truth's bad-record id union and the
clean sink is EXACTLY its complement, every clean row independently
re-checks as defect-free, every quarantine reason names its true defect's
field; a sample of clean records spread across all 4 markup versions
matches the catalog oracle field-for-field; completeness meets the
`0.98` target and the derived modeled cost is well under the all-render
cost and close to the mixed-strategy reference; and the metrics registry
exposes every required family with real movement (both `strategy="html"`
and `strategy="api"` fetch counts, at least two distinct quarantine
reasons, a multi-field completeness gauge, real latency observations).

### CP2 -- chaos + change detection (`validate_cp2.py`)

**Build:** the same pipeline, now run with `chaos=True` for day 0 and day
1 (the target cycles markup version by wall-clock instead of by product
id -- your extraction can't assume "this id defaults to version V"), plus
`changedetect.py`'s fingerprint index and `changed_between`.

**Checked:** extraction completeness (sampled against the catalog oracle,
day-appropriate overlay applied) stays above a robust threshold on BOTH
chaos runs, and neither client gets banned; `changed_between(0, 1, ...)`
against a sample mixing ~120 truly-changed and ~120 truly-unchanged ids
(oracle computed independently from `data/target-spec.json`'s cumulative
overlay, not from anything your code reports) returns EXACTLY the changed
subset, with a negative control (a known-unchanged id) proven NOT flagged;
and calling `build_fingerprint_index`/`changed_between` a second time with
identical arguments (simulating an interrupted-then-resumed run) converges
to the exact same, exactly-correct result -- no drift, no duplicates.

### CP3 -- design memo + green re-run (`validate_cp3.py`)

**Build:** fill in all seven sections of `DESIGN.md` -- architecture and
data flow, defense handling, the data-quality contract, change-detection
design, cost/budget tradeoffs, observability, and scaling to production/10x.

**Checked:** every required section has real content (no leftover
placeholder text, a minimum length, grounded in this capstone's actual
vocabulary), THEN `validate_cp1.py` and `validate_cp2.py` are re-run as
SUBPROCESSES and both must still pass. A design memo for a pipeline that no
longer converges, or that regressed on CP2's chaos/change-detection checks,
does not pass this checkpoint either.

## Completion criteria

From the **module root**:

```bash
uv run python 07-capstone-data-quality-platform/tests/validate_cp1.py
uv run python 07-capstone-data-quality-platform/tests/validate_cp2.py
uv run python 07-capstone-data-quality-platform/tests/validate_cp3.py
```

The task is complete when all three print `PASSED` and exit 0. CP1 and CP2
each run a real full-catalog crawl against the live target (CP1 once, CP2
twice under chaos) -- expect a few minutes per checkpoint, not seconds;
that is expected, not a bug to optimize away. Any failure -- a stub still
raising `NotImplementedError`, a banned client, a wrong quarantine split, a
markup version your fallback chain silently drops, a router that renders
too much or too little, a nonce leaking into a fingerprint, a non-idempotent
change-detection run, or an unfilled `DESIGN.md` -- prints a single
`NOT PASSED: <reason>` line and exits 1.

## Estimated evenings

3-4

## Topics to read up on

- Composing several independent scraping concerns (pacing, extraction,
  data-quality gating, cost routing, observability) into one pipeline
  without any of them silently depending on another's internal shape
- Fallback-chain HTML extraction under an adversarial "the shape changes
  mid-crawl" condition (chaos markup cycling), not just a fixed encoding
- Designing a fingerprint payload that structurally cannot leak volatile
  per-request noise, rather than remembering to strip it every time
- Idempotent incremental jobs: what "resuming after an interruption" needs
  to guarantee, and how to test for it without actually building crash
  injection
- Cost-aware routing combined with a data-quality gate operating on the
  same extracted record
- Designing Prometheus instrumentation that's useful in-process (no HTTP
  server required) as well as over `/metrics`

## Off-limits

`.authoring/design.md` (at the module root) holds the target site's full
defense/rendering/cost-model contract, the RNG draw order, and the
committed ground-truth values -- spoilers for this and every other task in
the module. Don't read it before finishing this task.

`data/catalog.json` and `data/target-spec.json` are the target's own
backend data (product corpus and defense/behavior config), not a task
scaffold -- reading them ahead of time trivializes the recon, extraction,
and quarantine decisions this capstone is built from. Only
`data/ground-truth.json` is committed and meant to be readable.
