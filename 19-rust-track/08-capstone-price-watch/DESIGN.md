# Capstone Design Memo — Price Watch

Fill in each section with your own analysis, grounded in what you actually
built and observed across CP1, CP2, and CP3 of this capstone — not generic
prose about bitcask or Parquet in the abstract. CP3's test suite reads this
file and checks that every section below is present, filled in, and long
enough to actually say something.

## Architecture and data flow

[fill in — walk through one product's journey end to end: a route on the
fixture server returns its JSON payload, `fetch_price` reads and parses it,
`ingest_batch` decides whether it's allowed to run yet (the concurrency
cap), `put_latest_price` decides whether it's fresh enough to write, and
`export_parquet` eventually reads it back out. Where does `Store` end,
and the price-specific domain layer (`put_latest_price` and friends) begin
— why did you draw that line where you did?]

## Concurrency cap and backpressure

[fill in — name the exact mechanism you used to enforce `concurrency_cap`
in `ingest_batch` and explain, concretely, what would happen to the
fixture server's observed `max_concurrency` if you removed it entirely.
Cite the actual `max_concurrency` values your CP3 run observed for at
least two different cap settings. What's the difference between "capped"
and "capped and actually reaches the cap under load" — why does this
capstone's test suite check both?]

## Bitcask persistence and crash recovery

[fill in — describe your on-disk record layout and keydir shape in your
own words, then walk through exactly what happens, byte by byte, when
`Store::open` encounters a record whose header is fully present but whose
value bytes were cut short by a truncation. What did your CP1/CP3 crash-
recovery tests actually prove about your implementation, concretely — not
just "it passed"?]

## Freshness and idempotent convergence

[fill in — explain why `put_latest_price` compares `scraped_at` instead of
simply overwriting on every successful fetch, and describe a concrete
scenario (drawn from this capstone's own CP2/CP3 tests, not a hypothetical)
where a naive "last arrival wins" implementation would have produced the
wrong final price. Why does resuming ingest after a simulated crash
converge to the correct state in your implementation, without needing to
know which records were lost?]

## Parquet export

[fill in — what three columns does your export produce, and what arrow
types did you choose for each, and why? Walk through how CP2's test reads
the file back independently of your own code and what specifically it
checks beyond "the file exists and has rows."]

## Scaling to production

[fill in — if the number of tracked products went from dozens to hundreds
of thousands, what in your current implementation would need to change
first: the store's single-file, single-keydir design, the ingest fan-out
strategy, the Parquet export cadence, something else? What's the first
thing that would actually break (not just "get slower"), and what's the
smallest change that would fix it? What would you add that this
capstone's checkpoints don't test at all — retries/backoff on ingest
failures, multiple concurrent writers to the store, incremental
(non-full-snapshot) Parquet export, alerting on stale products, anything
else you'd want before this ran unattended in production?]
