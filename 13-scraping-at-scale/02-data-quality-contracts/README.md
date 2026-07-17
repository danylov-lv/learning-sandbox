# 02 — Data quality contracts

## Backstory

Your crawler works. It walks the catalog, calls `GET /api/product/{id}`,
and gets back JSON. But "gets back JSON" and "gets back a USABLE record"
are not the same claim — about one in ten products on this target ships
with a planted defect: a price that's missing, non-numeric, or negative, a
currency code nobody issues, an empty title, a description that got cut
off mid-sentence. None of that is a network error. Every one of those
requests comes back `200 OK` with a syntactically valid JSON body — the
defect is INSIDE the record, not in the transport.

If nothing stands between "fetched" and "stored," every one of those bad
records flows straight into whatever depends on this data: a price feed
with negative numbers in it, a search index with blank titles, a currency
converter that chokes on `"XYZ"`. The fix isn't "try to clean it up
automatically" — some of these you genuinely can't repair from the record
alone (what was the real price supposed to be?). The fix is a GATE: an
explicit, machine-checked contract that every record has to pass before it
counts as clean, with a real destination — not `/dev/null` — for the ones
that don't.

## What's given

- `src/contracts.py` — a `build_product_schema()` stub that must return a
  `pandera.pandas.DataFrameSchema`. Its docstring lists every business rule
  the schema has to express: required/typed fields, a `price` rule
  (positive, present, below a sane ceiling), a `currency` allow-list
  (already given as `ALLOWED_CURRENCIES`), a non-empty `title` rule, and a
  rule for the one defect this file deliberately does NOT spell out for
  you — a corrupted description. Go look at a live record to find that
  signal; see the module README's task-01-style advice below.
- `src/gate.py` — three stubs:
  - `run_gate(records, workdir)` — validate a batch of records against the
    contract, split them, write a clean sink and a quarantine sink (with a
    `reason` per quarantined row), return a summary.
  - `field_completeness(records)` — a per-field non-null/non-empty rate,
    computed independently of schema validity.
  - `completeness_alert(completeness, thresholds)` — turn a completeness
    report into alerts for whichever fields dropped below their threshold.
- `harness/common.py` at the module root — `TargetClient` if you want to
  poke at the live target yourself while developing (recommended — you'll
  need to see what a defective record actually looks like before you can
  write a check for it). You do **not** need to write a crawler for this
  task: the validator fetches the graded record set itself (see below).

## What's required

1. Fill in `build_product_schema()` in `src/contracts.py` so it rejects
   every one of the six defect shapes and accepts every legitimate record.
   Decide deliberately whether the schema should be `strict` about unknown
   columns — this is a boundary contract, think about what you actually
   want to happen if an upstream change adds a field nobody told this
   schema about.
2. Implement `run_gate` in `src/gate.py`:
   - Normalize a `list[dict]` of `/api/product/{id}` response bodies into a
     single typed pandas DataFrame (decide what to do with the nested
     `shipping_info` object and the volatile `_nonce` field before handing
     the frame to the schema).
   - Validate with `lazy=True` so every failing row is captured, not just
     the first one pandera trips over.
   - Write passing records to `{workdir}/clean.jsonl` and failing records
     to `{workdir}/quarantine.jsonl` (one JSON object per line), each
     quarantined record annotated with a human-readable `reason` derived
     from pandera's `failure_cases`.
   - Return `{"clean_count", "quarantine_count", "clean_path", "quarantine_path"}`.
3. Implement `field_completeness` and `completeness_alert` in `src/gate.py`
   — a lightweight monitor that answers "is some field silently degrading
   over time," independent of whether individual values pass the strict
   contract (a `price` of `"N/A"` is "present" for completeness purposes
   even though it's invalid for contract purposes — those are two
   different questions).

Nothing in this task writes to a shared database — sinks are plain JSONL
files under whatever `workdir` you're given (a gitignored dir, or a temp
dir the validator hands you).

## Exploring the target while you work

This task's validator fetches the graded record set itself (day 0, every
product id) so grading stays deterministic — you don't write a fetch layer
here. But you still need to know what a defective record actually looks
like before you can write a schema that catches it. Use `harness.common.
TargetClient` (or plain `curl`/`httpx`) to pull a handful of `GET
/api/product/{id}` responses yourself during development — a modest range
of ids is enough to see all six defect shapes at least once. This is
exploring the LIVE target, not reading its backend files — `data/
catalog.json` and `data/target-spec.json` are off-limits (see the module
README and `.authoring/design.md`), the running site's own responses are
fair game.

## Completion criteria

From the **module root**:

```bash
uv run python 02-data-quality-contracts/tests/validate.py
```

The validator fetches all ~4,000 canonical records from the live target
(politely paced — this takes roughly a minute and a half, that's expected)
and, independently of your code, loads the true bad-record ids by defect
type from `data/ground-truth.json`. It then asserts:

- your quarantine sink contains **exactly** the bad-record ids — not a
  superset, not a subset;
- your clean sink contains **exactly** every other id, and every clean row
  independently re-checks as defect-free;
- every quarantined row's `reason` mentions the field its true defect
  actually touches (wording is free, the field is not);
- `field_completeness` matches an independent recompute within a small
  tolerance;
- `completeness_alert` fires on a synthetic batch with degraded field
  completeness and stays silent on a fully-complete one.

## Estimated evenings

1-2

## Topics to read up on

- pandera `DataFrameSchema` / `Column` / `Check`, lazy validation and
  `SchemaErrors.failure_cases`
- `strict` mode on a pandera schema and what it protects against at a
  data-quality boundary
- data quality dimensions: validity vs. completeness (why they're
  different monitors, not the same check twice)
- pandas dtype coercion and what happens when a column mixes types (e.g. a
  numeric column with one string value in it)

## Off-limits

`.authoring/design.md` and `data/catalog.json` / `data/target-spec.json`
are off-limits before you attempt this task — they contain the target
site's own backend data and the full spoiler-level design brief for this
module, including the exact bad-record ids. Read `.authoring/design.md`
after you're done, if you want the full story. Live requests to the
running target (`GET /api/product/{id}` and friends) are fine and expected
— that's the whole point of exploring "the target," not "the target's
backend files."
