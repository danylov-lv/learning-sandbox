# 03 -- Change detection and fingerprinting

## Backstory

Your team's scraper already crawls the catalog and stores full product
detail. It runs on a schedule -- once a day, say -- and every run currently
does the same thing: fetch all 4,000 products, all over again, from
scratch. That worked fine when the catalog was small. It does not scale,
and it's wasteful in a specific, measurable way: on this target, only ~4%
of products actually change from one day to the next (a price moves, or an
item goes in/out of stock). The other 96% of every run's work is spent
re-fetching and re-processing bytes that are already sitting in your store,
unchanged.

The fix is incremental re-scraping: on each run, figure out cheaply which
products actually changed, and only pay for full re-fetch/re-process on
that subset. "Cheaply" is the catch. You can't ask the target "what changed
since yesterday?" -- there's no such endpoint -- so the only way to know is
to fetch each product again and compare. The entire exercise is making that
comparison cheap and, above all, CORRECT: this target embeds a fresh random
value in every single response, unrelated to whether the underlying product
data changed at all. Hash the wrong thing and your "change detector" will
confidently report that all 4,000 products changed, every single day,
forever -- which is exactly the all-fetch-everything status quo you were
trying to get away from, just with extra steps.

## What's given

- `src/fingerprint.py` -- `fingerprint(payload)` stub. Turns one product's
  fetched data into a stable content hash. Its docstring documents exactly
  where this target's volatile nonce hides, per markup version and in the
  JSON API.
- `src/detect.py` -- `build_fingerprint_index(day, client_id, product_ids)`
  and `changed_between(day_prev, day_curr, client_id, product_ids)` stubs.
  This is the entrypoint: fetch, fingerprint, diff, report which ids
  changed.
- `tests/validate.py` -- the independent-oracle validator (see below).
- A gitignored `run/` directory (create it yourself if you want it) is a
  reasonable place to persist a per-day fingerprint index between runs --
  nothing shared reads or writes there.
- The target site at `http://localhost:8313` (already running via
  `docker-compose`), serving day-snapshots via `?day=0` (baseline) through
  `?day=4`. `harness/common.py` (module root) has `TargetClient` (a thin
  `httpx.Client` with browser-like default headers), `reset_client`, and
  `get_client_state` -- you still write your own fetch/pacing/retry logic,
  the harness only saves you from reinventing header plumbing.

## What's required

Implement `fingerprint()` in `src/fingerprint.py` and
`build_fingerprint_index()` / `changed_between()` in `src/detect.py`:

- `fingerprint(payload) -> str`: a stable hash of a product's OBSERVABLE
  data that excludes the volatile nonce (and any other per-request noise).
  Two fetches of the same unchanged `?day=` of the same product must
  produce the identical fingerprint.
- `build_fingerprint_index(day, client_id, product_ids=None) -> dict[int, str]`:
  fetch + fingerprint each product in `product_ids` (default: all real
  product ids) for `day`. This is the state a real incremental run
  persists between days.
- `changed_between(day_prev, day_curr, client_id, product_ids=None) -> set[int]`:
  the entrypoint -- return the set of ids whose fingerprint differs between
  the two days.

Both functions in `detect.py` must not get the calling client banned
(bounded concurrency + paced dispatch -- see `.authoring/design.md`'s
rate-limit numbers if you've already read it from an earlier task; if not,
the docstrings in `detect.py` restate the budget) and must never touch a
honeypot id or `/trap/*`.

## Completion criteria

```bash
uv run python tests/validate.py
```

The validator, independent of anything your code reports, computes the true
changed-id sets for a sampled subset of products straight from this
module's committed ground truth, then:

1. Builds a sample mixing ~120 ids known to change on day 1 with ~120 ids
   known to be unchanged on every day, resets a fresh client, calls your
   `changed_between(0, 1, client_id, product_ids=sample)`, and asserts the
   returned set is EXACTLY the changed subset -- no false positives (an
   unchanged id flagged -- your nonce-stripping has a gap), no false
   negatives (a changed id missed).
2. A negative control, independent of check 1: calls your own
   `build_fingerprint_index` twice for the same handful of always-unchanged
   ids (spanning all 4 markup versions), and asserts the two runs produce
   IDENTICAL fingerprints despite each fetch carrying its own fresh nonce.
3. A second, smaller day-1-to-day-2 sample with the same exact-match check,
   to confirm the mechanism isn't a one-day fluke.

It also asserts your client never gets banned during any of the above.
Prints `PASSED: ...` with the observed counts, or `NOT PASSED: <reason>`.

## Estimated evenings

1-2

## Topics to read up on

- Content hashing / fingerprinting for change detection
- HTTP conditional requests (`ETag`, `If-None-Match`, `Last-Modified`) as
  the server-side version of the same idea
- Canonicalization before hashing (stable serialization, why dict key order
  and float formatting matter)
- Incremental/delta crawling strategies

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the target's internal spec, the committed ground-truth values, and the
verification philosophy behind every task in this module -- spoilers.
Don't read it before finishing this task.

`data/ground-truth.json` is the validator's own oracle (that's how it
independently checks your answer) and it is fine to know it exists, but its
`change_days` field is the literal answer key for this task -- reading it
and returning those ids directly instead of actually fetching and
fingerprinting defeats the entire point of the exercise. Detect changes by
observing the target, not by reading the test's answer key.
