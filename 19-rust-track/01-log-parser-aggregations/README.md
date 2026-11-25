# 01 -- Log Parser & Aggregations

## Backstory

You've just inherited a small web-scraping/crawler service from a
colleague who left the company. Along with the codebase, you got a 27MB
`access.log` -- a year-one artifact nobody ever built tooling around,
because "it's just a log file, `grep` is fine." `grep` is fine for finding
a specific line. It is not fine for the questions your manager is actually
asking this week: what fraction of requests are erroring out, which
endpoints are hottest, and whether p99 latency has a problem worth paging
someone about. You need real aggregates, computed once, correctly, over
the whole file -- and you'd like to not read all 27MB into memory to get
them, because this log rotates in daily and next month's version won't be
this small.

This is also, not coincidentally, a solid first Rust project: a log line
is a string with a fixed-ish shape, which is exactly the setting where
`&str` borrowing, `Result`-based error handling, and iterator-driven
aggregation all earn their keep instead of feeling like ceremony.

## What's given

- `src/lib.rs` -- the scaffold you fill in: `LogEntry<'a>` (a borrowed
  view of one parsed line), `LogParseError` (a custom error enum with
  `Display`/`Error`/`From` impls), `parse_line`, `status_class`,
  `LogStats` and `ResponseTimeStats` (the aggregate results), `aggregate`
  (streams a `BufRead` and folds it into `LogStats`), `percentile`, and
  `top_paths`. The exact line format is documented in the module-level
  doc comment at the top of the file -- read it before writing any code.
- `src/main.rs` -- a thin CLI stub over the library (not graded, but a
  nice sanity check once the library works: `cargo run -p
  t01-log-parser-aggregations`).
- `tests/parse_line.rs`, `tests/aggregate_hand_built.rs`,
  `tests/aggregate_ground_truth.rs` -- the validator. See "Completion
  criteria" below.
- `sandbox18-harness` as a dependency, giving you
  `sandbox18_harness::ground_truth::{data_path, load}` for locating and
  reading `data/access.log` and `data/ground-truth.json`.
- `data/access.log` and `data/ground-truth.json` at the module root, via
  `cargo run -p sandbox18-datagen` (run it first if `data/` is empty --
  see the module README).

## What's required

1. **`parse_line`**: given one line of `access.log`, return a `LogEntry`
   whose string fields (`ip`, `timestamp`, `method`, `path`) all borrow
   from the input line -- no per-field `String` allocation -- or an `Err`
   describing what didn't match the expected shape. Malformed input
   (roughly 1.5% of the real file: stripped brackets, a non-numeric
   status, a truncated line, stripped quotes, a trailing garbage token)
   must come back as `Err`, never a panic and never a best-guess
   `LogEntry`.
2. **`LogParseError`**: a custom enum implementing `std::error::Error` and
   `Display`, with `From<ParseIntError>` / `From<ParseFloatError>`
   conversions so `parse_line` can use `?` on every numeric field.
3. **`aggregate`**: takes anything implementing `BufRead` (so the caller
   controls whether that's a 27MB file or a 12-byte test string) and
   streams it line-by-line -- via `BufRead::lines()`, not by reading the
   whole input into one `String` first -- parsing each line and folding
   the results into a `LogStats`: total/well-formed/malformed line
   counts, status-class counts, method counts, the full path histogram,
   unique IP count, 5xx error rate, and response-time statistics.
4. **`percentile`** and **`top_paths`**: the two pieces of `aggregate`
   worth pulling out as their own testable functions -- nearest-rank
   percentile computation, and a stable top-N ranking with a tiebreak
   rule.

## Completion criteria

From this task's directory (or the module root with `-p
t01-log-parser-aggregations`):

```bash
cargo test -p t01-log-parser-aggregations
```

All given tests passing means:

- `parse_line` correctly parses well-formed lines and correctly rejects
  every corruption mode present in the real data, plus edge cases (empty
  line, whitespace-only line).
- `aggregate` produces exactly the right counts on small, hand-built
  inputs with expectations you can verify by eye, including an
  empty-input case that must not panic.
- `aggregate` run over the *real* `data/access.log` matches
  `data/ground-truth.json` -- loaded through the harness, never
  re-derived from your own code a second way -- on every field: line
  counts, status/method/path histograms, top paths, unique IPs, 5xx rate,
  and response-time percentiles (the last with a small tolerance, since
  the log file itself stores response times rounded to one decimal
  place while the ground truth was computed from full precision).

If you're unsure whether an implementation is "done enough," the tests
are the actual bar -- a constant-returning or single-hardcoded-entry
version will fail multiple tests immediately, since the real corpus has
multiple status classes, methods, and paths.

## Estimated evenings

1-2

## Topics to read up on

- Ownership and borrowing: why a function can return data borrowed from
  its input, and what that does (and doesn't) cost at runtime
- `&str` vs `String`: when a slice suffices and when an owned string is
  genuinely required (hint: it's about lifetimes, not about "these are
  the same thing with different performance")
- Iterator adapters (`filter_map`, `fold`, `entry` on `HashMap`) as an
  alternative to index-based loops
- `Result`, the `?` operator, and the `From` trait's role in letting `?`
  convert between error types automatically
- Implementing `std::error::Error` and `std::fmt::Display` for a custom
  error enum
- `HashMap` as an aggregation accumulator: `entry().or_insert()` /
  `entry().or_default()`
- `BufRead` / `BufReader::lines()` for streaming line-oriented input,
  versus `std::fs::read_to_string`
- Percentiles / order statistics: what "p95" or "p99" actually means as a
  computation over a sorted sample
- Zipf-distributed popularity and log-normal latency: why real traffic
  and latency data are skewed rather than uniform or normal, and what
  that implies for which summary statistics are meaningful

## Off-limits until you're done

`.authoring/design.md` at the module root documents this task's grading
internals -- read it after you've passed the tests, if at all, not before.
