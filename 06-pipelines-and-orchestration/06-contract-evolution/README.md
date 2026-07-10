# 06 — Contract evolution

## Backstory

Your gate from task 05 has been running quietly and doing its job. Then the
upstream scraping team changes something and doesn't tell you — because they
never tell you, that's the whole reason the gate exists. Twice.

This task is about living through both changes without silently loading
garbage and without your existing downstream consumers noticing anything
broke.

## What's given

- Your own `contracts.py` and `dags/t05_contract_gate.py` from task 05 — this
  task evolves them, it doesn't replace them. There is no new DAG id; you
  keep running `t05_contract_gate`, you just change what it accepts and how
  it gets there.
- `src/downstream_check.sql` — a stand-in for a report that was already
  built on top of `core.price_records` before any of this happened: daily
  per-category row count / avg / min / max price. It does not reference
  `seller_rating`. It must keep returning rows for every loaded day, before
  and after you touch anything.

## What's required

### Step 1 — point the gate at 2025-06-10

Run `t05_contract_gate` for `2025-06-10`. Your strict schema from task 05
rejects the batch — there's a column it doesn't recognize. Before you just
add the column and move on, notice what actually happened: this isn't a
handful of rows with a bad price or a missing url, it's *every* row in the
batch failing the same way, for the same reason. That's a different kind of
failure than task 05's contract was designed to report, and it deserves a
different response:

- Detect that this is a schema-level drift, not row-level invalid data.
- Send an alert (`POST http://alert-sink:8000/alert`) with at minimum:
  `type` set to `"contract_drift"`, `dt` set to the day's date string, and
  some field describing what changed (name it what you like — a human
  reading `data/alerts/alerts.ndjson` later should be able to tell what
  happened without opening the DAG code).
- Do not silently load a partial or malformed batch. Either the whole day
  gets quarantined pending a decision, or the run halts — your call, but it
  must be a deliberate, visible outcome, not rows quietly missing from
  `core`.

### Step 2 — evolve the contract, additively

`core.price_records` already has a nullable `seller_rating real` column
(from task 05's DDL). Update your pandera schema so it accepts an *optional*
`seller_rating` — present or absent, both valid — without loosening anything
else. Rerun `t05_contract_gate` for `2025-06-10` and confirm it now loads
cleanly, with `seller_rating` populated where the source data has it.

### Step 3 — point the gate at 2025-06-12

Same drill, different failure: `price` shows up as a formatted string
instead of a number (`"$1,299.00"`-style, or `"1.299,00 EUR"`-style — two
different locale conventions, mixed within the same day's data). Detect it
as drift the same way you did in step 1, alert on it the same way, don't
load garbage.

Then write a normalizer that runs *before* your pandera schema sees the
`price` column: given a raw value that might be a JSON number (leave it
alone) or a formatted string in either locale style, produce the correct
numeric price. Both styles appear in the same file — your normalizer has to
disambiguate per value, not per day. Wire it into the pipeline as a
pre-validation step, then rerun `2025-06-12` and confirm it loads.

### Step 4 — prove downstream didn't break

Run `src/downstream_check.sql` against the warehouse (`psql`, or a quick
`psycopg` script — your call) and confirm it still returns rows for every
day you've loaded so far, including `2025-06-10` and `2025-06-12`. It should
never have needed to change.

### Step 5 — backfill

Run the now-fully-evolved gate across `2025-06-06` through `2025-06-14`
(some of those days you may have already touched in earlier steps — running
them again should be a no-op, per task 05's idempotency work). All 14 days
(`2025-06-01` through `2025-06-14`) should now be sitting in
`core.price_records`.

## Completion criteria

`uv run python tests/validate.py` from this task's directory passes. Beyond
what task 05 checked, it verifies: all 14 days present in `core` with counts
and per-currency price sums matching ground truth (including the
locale-formatted-price days — this is the proof your normalizer is
correct), `seller_rating` populated from `2025-06-10` onward and entirely
absent before it, `data/alerts/alerts.ndjson` contains `contract_drift`
alerts referencing both `2025-06-10` and `2025-06-12`, `downstream_check.sql`
returns rows for all 14 days, and that no post-evolution `2025-06-10`+ rows
are sitting in quarantine purely because of the drift you've since
accommodated (the genuinely invalid ~1% of records every day still belong
there).

## Estimated evenings

1-2

## Topics to read up on

- pandera schema versioning / additive schema evolution patterns
- detecting systemic vs. row-level validation failures (what does "every row
  fails the same check" tell you that "1% of rows fail assorted checks"
  doesn't?)
- locale-specific number formatting conventions (thousands vs. decimal
  separator conventions across locales)
- alerting from within a DAG task (HTTP calls from task code, and why that's
  different from Airflow's own callback/SLA-alerting machinery)
- backfill semantics in Airflow (`catchup`, running a DAG across a date
  range, and why idempotency from task 05 matters here)
