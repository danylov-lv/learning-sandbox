# Notes for future sessions on module 06 data/infra (part 1: generator)

Companion to `design.md`. This file is operational gotchas, not the contract
itself — read `design.md` first.

## Gitignore negation gotcha

The repo root `.gitignore` has `**/data/`, which excludes the whole `data/`
directory tree, not just its contents. Git's docs are explicit: once a
directory is excluded, nothing under it is re-checked against later rules —
so a naive `!data/ground-truth.json` in the module `.gitignore` does nothing
on its own, because git never descends into an already-excluded directory.

The fix used here (`06-pipelines-and-orchestration/.gitignore`):

```
!data/
data/*
!data/ground-truth.json
```

`!data/` re-includes the directory itself (so git will look inside it),
`data/*` re-excludes everything directly under it, and the final `!` carves
out the one file that should be tracked. Verified with `git status --ignored`
and `git add -n` (not just `git check-ignore -v`, which reports the last
*matching* pattern even when that pattern is a negation and doesn't reliably
signal the final ignored/not-ignored outcome by itself).

Note: modules 04 and 05 do not actually have a module-level `.gitignore` and
do not commit their `ground-truth.json` (checked via `git ls-files` — empty
match). The brief for this module explicitly wants `ground-truth.json`
committed, so module 06 diverges from 04/05's actual (not just documented)
behavior here on purpose.

## Dependency versions

`pyproject.toml` deps were added via `uv add <package> ...` rather than
hand-typed pins, so the versions in `uv.lock` are whatever was current and
mutually resolvable at generation time (2026-07-09) — notably `pandas==3.0.3`,
`pandera==0.32.1`, `prefect==3.7.7`, `dbt-core`/`dbt-postgres` ~1.11/1.10,
`psycopg==3.3.4`. If a later task needs a specific dbt-postgres/dbt-core pair
for compatibility, re-pin explicitly and re-run `uv lock`.

## Generator internals worth knowing before extending

- Single `np.random.default_rng(60606)` stream drives everything, draws
  happen in a fixed order (universe build, then day 0's counts, then day 0's
  fresh/late/invalid/dup/malformed draws, then day 1, ...). Inserting a new
  random draw anywhere in that sequence changes every downstream value for
  every later day — regenerate ground-truth.json and re-verify if you touch
  `generate.py`'s draw order.
- `Universe.category_product_ids` / `category_product_weights` are built once
  from the *global* per-product popularity permutation, sliced per category —
  this is why sampling within a category via `sample_products()` is cheap
  (no re-normalization per call).
- Late-arriving records for day N are sampled from day N-1's `valid_pairs`
  list, which is `(source_site, product_id, category)` tuples — not just
  `product_id` — because a late-arriving record must keep the same source. day
  0 has no predecessor, `LATE_ARRIVING_RATE` is force-zeroed for it in
  `generate()` (`late_n = ... if day_idx > 0 else 0`).
- `mart_reference` for pre-drift days is computed by re-parsing the just-built
  `valid_lines` JSON immediately after building them (before insertion into
  the shuffled/duplicated/malformed-injected file) — this is intentional:
  it's the generator reading back its own still-numeric-price output, not
  "re-deriving ground truth by parsing the poisoned file," which the brief
  forbids. Once `price_is_string` flips true, `price_sum` is dropped entirely
  from that day's `mart_reference` per the design doc.
- Malformed-line kind 0 (truncated) slices an already-*shuffled* line from
  that day's `base_lines`, so which record gets truncated is itself
  seed-derived and reproducible, not tied to original generation order.

## Verification performed this session

- `SCALE=0.05` smoke run: 14 files written in well under a second, ~1.5k-3k
  lines/day.
- `SCALE=1.0` full run: see per-day counts and runtime reported in the
  completion summary — both were re-derived from ground-truth.json rather
  than eyeballed.
- Ad hoc checks (script written to `scratch/`, run, then deleted per
  CONVENTIONS.md — not committed):
  - Per-day identity `total_lines == malformed_lines + duplicate_lines +
    valid_records + invalid_records["total"]` holds for all 14 days at both
    scales.
  - Every line in every malformed line's file position fails `json.loads`
    (checked by attempting to parse every line in every day's file and
    comparing the failure count to `malformed_lines`).
  - Days `>= 2025-06-10` have `seller_rating` on 100% of sampled valid lines;
    earlier days have it on 0%.
  - Days `>= 2025-06-12` have `price` as a JSON string on valid lines; earlier
    days have it as a JSON number. Invalid lines' `price` is always a JSON
    number on every day, drift or not.
  - Rerunning `generate.py` at the same `SCALE` twice produced byte-identical
    NDJSON files and an identical `ground-truth.json` (hashed both runs).

## Follow-up: `per_day_currency` (coordinator request, same session)

- Added top-level `per_day_currency` to ground-truth.json: per day per
  currency `count` + `price_sum` of the TRUE planted numerics, all 14 days
  including drift days. See design.md field notes for exact semantics and the
  exact-round-trip guarantee for the formatted price strings.
- Implemented with zero RNG impact: `build_valid_record` now *returns* the
  `round(price, 2)` numeric it already computed (no draws added, removed, or
  reordered), and callers thread it up as `(currency, numeric)` tuples.
  Verified: sha256 of all 14 NDJSON files identical before/after the change
  at SCALE=1.0.
- Verified via throwaway scratch check (deleted after): per-day currency
  counts sum to `valid_records`; pre-drift days match `mart_reference`
  exactly; drift-day re-parse of the price strings reproduces planted counts
  exactly and sums within 0.02; every drift-day price string parses back to
  an exact 2-decimal value.
