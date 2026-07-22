# 18 — Rust Track

## What this track covers

An independent-pace track of eight small Rust projects plus one optional
bonus. There is no chapter binding — you're early in the book, so each
task stands alone and lists the idioms it exists to cement rather than
assuming a fixed prior lesson. Pick this up whenever, alongside the main
data-engineering track.

The tasks mix four flavors:

- **From your world** — a log parser with aggregations, a multithreaded
  URL health checker, a CSV-to-Parquet converter: things that look like
  the data-engineering work you already do, now in Rust.
- **New territory** — a TUI dashboard with `ratatui`, something you
  haven't built in any language yet.
- **Applied** — a bitcask-style key-value store with real crash recovery,
  the kind of small systems project that teaches file-format thinking.
- **Rust-specific** — a toy expression interpreter (ownership + enums +
  pattern matching, deliberately built to showcase them) and an optional
  proc-macro bonus at the end.

No async appears until tasks 07 and 08. Everything before that is
threads, channels, and plain blocking I/O — async is introduced once you
have the synchronous mental model solid.

## Stack

This is a **Rust module**: no Python, no `docker-compose.yml`, no host
ports. The Cargo workspace at the module root replaces all of that.
Shared dependencies (`serde`, `arrow`/`parquet`, `ratatui`/`crossterm`,
`tokio`, `tempfile`, `syn`/`quote`/`proc-macro2`) are pinned once in the
root `Cargo.toml`'s `[workspace.dependencies]`; each task just writes
`some-dep.workspace = true`. `Cargo.lock` is committed, so every task
builds against the exact same resolved versions.

Prerequisites: a Rust toolchain (`rustc`/`cargo`), installed via
`rustup`. Network access to crates.io only for the first build, which
compiles `arrow`, `parquet`, `ratatui`, and `tokio` and is noticeably
slower than every build after it.

## Getting started

```bash
cd 18-rust-track
cargo run -p sandbox18-datagen   # generates data/access.log, data/products.csv, data/ground-truth.json
```

Generate the data once before starting tasks 01, 03, 06, or 08 — they read
from `data/`, which is gitignored (only `ground-truth.json` is
committed). `sandbox18-datagen` honors a `SCALE` env var (default `1.0`)
if you want a smaller dataset for faster iteration:
`SCALE=0.1 cargo run -p sandbox18-datagen`.

Then, per task, run its test suite from the module root:

```bash
cargo test -p t01-log-parser-aggregations
```

A task is done when `cargo test -p <package>` passes. Rust's own non-zero
exit on a failing or panicking test is this module's stand-in for the
repo-wide "print `NOT PASSED: <reason>` and exit 1" validator convention —
every given test's assertions carry an explanatory message, so a failure
tells you what broke, not just that something did.

## Tasks

| # | Task | Flavor | Evenings |
|---|------|--------|:---:|
| 01 | log-parser-aggregations | from your world | 1–2 |
| 02 | toy-expression-interpreter | Rust-specific | 2 |
| 03 | csv-to-parquet | from your world | 2 |
| 04 | url-health-checker | from your world | 1–2 |
| 05 | bitcask-kv-store | applied | 2–3 |
| 06 | tui-log-dashboard | new territory | 2 |
| 07 | async-fetch-pipeline | async | 2 |
| 08 | capstone-price-watch | async, capstone | 3–4 |
| bonus | proc-macro-bonus | Rust-specific, optional | 1–2 |

Total: roughly 15–20 evenings, capstone included, bonus excluded.

- **01** — parse a realistic, partly-malformed web access log and
  reproduce a set of aggregates (status-code breakdown, per-path counts,
  response-time percentiles) against an independently computed answer
  key. Ownership, `Result` + `?`, a custom error enum, iterator chains.
- **02** — a tokenizer and recursive-descent evaluator for a small
  arithmetic expression language. Enums, exhaustive `match`, `Box<Expr>`
  recursion, lifetimes, error types that carry a position.
- **03** — convert a scraped-product CSV (with a few dirty rows) into
  Parquet using `arrow`/`parquet`: typed schema mapping, record batches,
  writer options like compression and row-group size.
- **04** — check a list of URLs concurrently against a local fixture
  server with a fixed thread pool. `thread::scope`, `mpsc` channels,
  `Arc<Mutex<..>>`, trait objects for injectable checkers. No async.
- **05** — a bitcask-style append-only key-value store: binary record
  framing, an in-memory keydir, crash recovery by log replay, compaction.
- **06** — a live TUI dashboard tailing the access log with `ratatui` and
  `crossterm`. Graded by driving a pure `App` state struct directly and by
  asserting on a `TestBackend` buffer — never by screenshotting a real
  terminal.
- **07** — an async pipeline fetching many URLs under a hard concurrency
  cap, with `tokio`, `JoinSet`, `Semaphore`, timeouts, and retry with
  backoff.
- **08** (capstone, multi-evening) — async ingest → parse → bitcask-style
  store → Parquet export, in three checkpoints (CP1/CP2/CP3).
- **bonus** — a `#[derive(...)]` proc macro with `syn`/`quote`. Entirely
  optional; skip it if proc macros don't interest you yet.

## How the fixture server works (tasks 04, 05's tests, 07, 08)

There is no real network access in this module's tests and no HTTP client
crate anywhere (no `reqwest`, no `hyper`, nothing) — every task that needs
"a website to talk to" writes its own tiny HTTP/1.1 client over
`std::net::TcpStream` (or, for 07/08, `tokio::net::TcpStream`) and points
it at a local fixture server the GIVEN `sandbox18-harness` crate spins up
on an ephemeral port. This keeps the whole module offline and
deterministic, and it means you actually write the HTTP request/response
parsing yourself instead of outsourcing it to a crate — a `GET /path
HTTP/1.1\r\n...` request line and a status-line-plus-headers response are
not much code, and writing them is part of the point of tasks 04 and 07.

## No reference solutions

As with every module in this repo, there are no reference solutions
anywhere — not in hints, not in `.authoring/`, not in tests. Hints (in
each task's `hints/`) narrow progressively from a direction to a specific
mechanism to something close to pseudocode, but never hand you working
code.

## `.authoring/` is off-limits until after a task

`.authoring/design.md` documents the harness API contract, the ground-truth
schema, and the grading philosophy behind every task's tests — reading it
before you finish a task tells you more than you want to know going in.
Read it afterward, if at all, same rule as every other module.
