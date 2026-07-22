# 18-rust-track — authoring design (spoiler contract)

Off-limits to the learner before finishing a task, same rule as every other
module in this repo. This document is for task-authoring agents and future
generation sessions.

## Module shape

This is a Rust module: no Python, no `pyproject.toml`, no `uv.lock`, no
`docker-compose.yml`, no host ports. The Cargo workspace at
`18-rust-track/Cargo.toml` replaces all of that. Edition 2024, resolver
"3", `rust-version = "1.95"`. Every member writes `dep.workspace = true`
against `[workspace.dependencies]` in the root manifest rather than pinning
its own versions.

Resolved dependency versions (`Cargo.lock`, committed): serde 1.0.229,
serde_json 1.0.151, arrow 59.1.0, parquet 59.1.0, ratatui 0.30.2,
crossterm 0.29.0, tokio 1.53.1, tempfile 3.27.0, syn 2.0.119, quote 1.0.47,
proc-macro2 1.0.107.

## The eight tasks + bonus, in order

01. **log-parser-aggregations** (`t01-log-parser-aggregations`, std only).
    Parses `data/access.log` (Combined-Log-Format-ish, with a response-time
    field appended) and reproduces the aggregates in
    `ground_truth.log`. Idioms to cement: ownership, `&str` vs `String`,
    borrowing, iterator chains (`filter_map`, `fold`, `Itertools`-free),
    `Result` + `?`, a custom error enum implementing `std::error::Error`
    with `From` conversions (e.g. from `ParseIntError`), `HashMap`
    aggregation. Malformed lines (~1.5% of `total_lines`) must be *skipped,
    not silently miscounted* — the task's test suite checks
    `well_formed_lines + malformed_lines == total_lines` and that the
    aggregates match `ground_truth.log.*` computed over well-formed lines
    only.

02. **toy-expression-interpreter** (`t02-toy-expression-interpreter`, std
    only). A small arithmetic expression language (numbers, `+ - * /`,
    parens, maybe variables) — tokenizer over `&str` with lifetimes,
    `enum Expr { Num(f64), Add(Box<Expr>, Box<Expr>), ... }` recursion,
    exhaustive `match` for both parsing and evaluation, an error type that
    carries a byte/char position so error messages can point at the
    offending token. No ground-truth file dependency — this task's tests
    are self-contained example expressions with known results (division by
    zero, unbalanced parens, unknown token) since it doesn't touch the
    generated data at all.

03. **csv-to-parquet** (`t03-csv-to-parquet`). Reads `data/products.csv`
    (id, sku, category, price, in_stock, scraped_at — with ~2% dirty rows:
    empty/negative/`N/A` price, missing sku, bad boolean, bad timestamp)
    and writes a Parquet file via `arrow`/`parquet`. Idioms: traits and
    generics for a typed schema mapping, `RecordBatch`/`ArrayBuilder`
    construction, `WriterProperties` (compression codec, row-group size),
    `impl Trait` in a row-parsing iterator, error conversion across the
    `csv-parsing-error` / `arrow::error::ArrowError` boundary. Grading
    reads the Parquet file back and compares row counts, dtypes, and the
    `csv_ground_truth` aggregates (`category_price_stats`,
    `overall_price_stats`) — never the learner's own re-derivation.

04. **url-health-checker** (`t04-url-health-checker`, **no async**). Spins
    up `sandbox18_harness::fixture_server::FixtureServer` with a mix of
    routes (`/ok`, `/slow` with a delay, `/flaky` with `fail_first(n)`,
    a 404 default), then checks a list of URLs concurrently with a fixed
    thread pool. Idioms: `std::thread::scope`/`spawn`, `mpsc` channels for
    collecting results, `Arc<Mutex<..>>` for shared state, a
    `trait HealthCheck: Send + Sync` so the checker is injectable/testable
    with a fake, per-request timeouts via `TcpStream::connect_timeout` /
    `set_read_timeout`. Grading asserts against `server.stats()` — total
    requests observed, and (for the retry-logic sub-task) that a
    `fail_first(2)` route eventually reports success without exceeding a
    max-retries budget.

05. **bitcask-kv-store** (`t05-bitcask-kv-store`). A log-structured KV
    store: `BufWriter` appends framed records (key len, value len, key
    bytes, value bytes, maybe a CRC) to an append-only file; an in-memory
    `keydir: HashMap<Vec<u8>, RecordLocation>` maps keys to (file offset,
    length); startup replays the log to rebuild the keydir (crash
    recovery); a `compact()` method rewrites only live records. Idioms:
    `BufReader`/`BufWriter`, binary framing (`u32`/`u64` little-endian via
    `to_le_bytes`/`from_le_bytes`), `Drop` for a clean fsync-and-close, a
    `get` that returns a borrowed/copied slice deliberately distinguished
    from a `put` that takes owned `Vec<u8>`. Uses `tempfile` in its own
    tests (dev-dependency) to get a scratch directory per test. Grading:
    write N keys, kill the store mid-write by truncating the log file at a
    byte offset that lands inside a record, reopen, and assert the keydir
    recovered exactly the records that were fully flushed — never fewer,
    never a corrupted partial record accepted as valid.

06. **tui-log-dashboard** (`t06-tui-log-dashboard`). Tails `data/access.log`
    (or a synthetic growing copy) and renders a live `ratatui` dashboard:
    requests/sec, status-code breakdown, top paths. Idioms: a pure
    `App` state struct (counts, a ring buffer of recent lines) updated by
    an `enum Event { Tick, NewLine(String), Resize(u16,u16), Quit }` — the
    testable seam. Grading never screenshots a real terminal: it drives
    `App::handle_event` directly and asserts on the resulting state, and
    separately renders the `App` into a `ratatui::backend::TestBackend`
    buffer and asserts on specific cell contents (a header string, a path
    name, a count). `crossterm` is only used in the real `main.rs` event
    loop, which the tests never execute.

07. **async-fetch-pipeline** (`t07-async-fetch-pipeline`, `tokio`). Fetches
    a batch of URLs against `sandbox18_harness::async_fixture_server`
    (the `async` feature of the harness) under a hard concurrency cap.
    Idioms: `tokio::task::JoinSet`, `tokio::sync::Semaphore` for the cap
    (grading asserts `stats.max_concurrency <= cap`, never a wall-clock
    timing gate), `tokio::time::timeout` per request, retry with
    exponential backoff against `fail_first(n)` routes, structured
    shutdown (a cancellation token or a closed channel, not `abort()`
    everywhere), `async fn` in a trait (native, edition 2024 — or boxed
    futures if the task wants to show both).

08. **capstone-price-watch** (`t08-capstone-price-watch`, multi-evening).
    Async ingest (poll the async fixture server for "price" JSON payloads)
    → parse → store in a bitcask-style log (reusing the shape from task 05,
    not literally importing t05's crate — each task crate is standalone
    per the repo's task-isolation convention) → periodic Parquet export via
    arrow/parquet. Checkpoints: **CP1** ingest + bitcask persistence
    (`cargo test -p t08-capstone-price-watch --test cp1`), **CP2** adds the
    Parquet export and end-to-end freshness checks, **CP3** adds
    concurrency-cap and crash-recovery checks re-running CP1/CP2. Uses
    `tempfile` as a dev-dependency for scratch storage per test.

Bonus. **proc-macro-bonus** (`t09-proc-macro-bonus`, optional, `proc-macro
= true` crate). A `#[derive(...)]` macro using `syn`/`quote`/`proc-macro2`
— e.g. deriving a `Describe` trait that prints field names, or a
`Builder` derive. Graded via `trybuild`-free plain integration tests in
`tests/` that apply the derive to a local struct and assert on generated
behavior (never on generated *source text* — that would be an
implementation-detail check).

## Grading contract (the module's documented CONVENTIONS.md exception)

Every task is graded by GIVEN cargo integration tests under the task's own
`tests/` directory. **`cargo test -p <package>` is the validator.** Rust
tests exit non-zero on any failing/panicking assertion, and `cargo test`
prints the failing assertion's message — this already satisfies the
repo-wide "print `NOT PASSED: <reason>` and exit 1, no raw tracebacks" rule
without extra plumbing. This module documents that as its one exception to
the literal convention. Because of this, **every given test's assertion
must carry an explanatory message**: `assert_eq!(a, b, "why this
should hold and what it means if it doesn't")` or `assert!(cond, "...")` —
never a bare `assert!(cond)` with no context, since the message *is* the
diagnosis a learner gets instead of a validator's printed reason string.

## Anti-cheat / verification philosophy (inherited from the rest of the repo)

- Tests compare against `ground-truth.json` (tasks 01, 03, 06, 08) or an
  independently recomputed / hand-authored expectation (tasks 02, 04, 05,
  07, 09) — **never** against the learner's own output re-derived a second
  way that could share the same bug.
- A constant-returning or degenerate implementation must fail: e.g. task
  01's tests check more than one status class and more than one path
  count, so returning `HashMap::new()` or a single hardcoded entry fails
  immediately; task 05's tests write more keys than fit in one flush
  buffer and read them back in a different order than written; task 06's
  `TestBackend` assertions check cell contents that change between two
  different `App` states, so a `render()` that ignores `self` fails.
  Task-authoring agents must apply this same "would a stub implementation
  survive this test" check to every assertion they write.
- Timing is never an absolute wall-clock gate. Concurrency caps are
  checked structurally (`stats.max_concurrency <= cap`, from
  `fixture_server`/`async_fixture_server`'s own atomic counters — not from
  the learner's code), and retry/backoff is checked by request *count*
  against `fail_first_n`, not by measuring elapsed wall-clock time.
- `fixture_server` / `async_fixture_server` bind to `127.0.0.1:0`
  (ephemeral port) always. No task in this module claims a fixed host
  port, and no task depends on a real network call — the `RouteConfig`
  knobs (`status`, `body`, `with_delay`, `fail_first`) are the only
  externally-observable behavior a test needs to script.

## Harness API surface (`sandbox18-harness`, `harness/src/`)

Task-authoring agents write tests against these signatures. Do not
restate or duplicate this logic inside a task crate — depend on the
harness.

```rust
// ground_truth.rs
pub fn module_root() -> PathBuf;                 // walks up from CARGO_MANIFEST_DIR
pub fn data_path(name: &str) -> PathBuf;         // module_root().join("data").join(name)
pub fn load() -> GroundTruth;                    // reads + parses data/ground-truth.json

pub struct GroundTruth { pub seed: u64, pub scale: f64, pub log: LogGroundTruth, pub csv: CsvGroundTruth }
pub struct LogGroundTruth {
    pub total_lines: u64, pub well_formed_lines: u64, pub malformed_lines: u64,
    pub status_class_counts: BTreeMap<String, u64>,   // "2xx".."5xx"
    pub method_counts: BTreeMap<String, u64>,
    pub path_counts: BTreeMap<String, u64>,           // full histogram, well-formed lines only
    pub top_paths: Vec<PathCount>,                    // top 10, count desc, path asc tiebreak
    pub unique_ips: u64,
    pub error_rate_5xx: f64,
    pub response_time_ms: ResponseTimeStats,          // mean/p50/p95/p99/max, ms
}
pub struct CsvGroundTruth {
    pub total_rows: u64, pub valid_rows: u64, pub dirty_rows: u64,
    pub in_stock_count: u64, pub out_of_stock_count: u64,
    pub category_counts: BTreeMap<String, u64>,               // valid rows only
    pub category_price_stats: BTreeMap<String, PriceStats>,
    pub overall_price_stats: PriceStats,
}
pub struct PriceStats { pub count: u64, pub min: f64, pub max: f64, pub mean: f64, pub sum: f64 }

// fixture_server.rs (std, always available)
pub struct RouteConfig { pub status: u16, pub body: Vec<u8>, pub content_type: String, pub delay: Duration, pub fail_first_n: usize }
impl RouteConfig {
    pub fn new(status: u16, body: impl Into<Vec<u8>>) -> Self;
    pub fn with_delay(self, d: Duration) -> Self;
    pub fn with_content_type(self, ct: impl Into<String>) -> Self;
    pub fn fail_first(self, n: usize) -> Self;   // first n requests to this route: connection dropped, no response
}
impl FixtureServer {
    pub fn builder() -> FixtureServerBuilder;
    pub fn base_url(&self) -> String;            // "http://127.0.0.1:{port}"
    pub fn port(&self) -> u16;
    pub fn stats(&self) -> ServerStats;
}
impl FixtureServerBuilder {
    pub fn route(self, path: impl Into<String>, config: RouteConfig) -> Self;
    pub fn default_route(self, config: RouteConfig) -> Self;   // default: 404
    pub fn start(self) -> FixtureServer;         // binds 127.0.0.1:0, spawns accept thread
}
pub struct ServerStats { pub total_requests: u64, pub max_concurrency: u64, pub requests_by_path: HashMap<String, u64> }
// Drop on FixtureServer stops the accept loop and joins the thread.

// async_fixture_server.rs — identical shape, behind the harness `async` feature:
// AsyncFixtureServer::builder()... .start().await; async fn stats(&self) -> ServerStats;
// async fn shutdown(&mut self) for a deterministic awaited stop (Drop alone only signals, doesn't block).

// prng.rs
pub struct Xorshift64;
impl Xorshift64 {
    pub fn new(seed: u64) -> Self;
    pub fn next_u64(&mut self) -> u64;
    pub fn next_u32(&mut self) -> u32;
    pub fn next_f64(&mut self) -> f64;                  // [0, 1)
    pub fn gen_range(&mut self, lo: u64, hi: u64) -> u64;
    pub fn next_standard_normal(&mut self) -> f64;       // Box-Muller
    pub fn zipf_rank(&mut self, n: usize, s: f64) -> usize;
}

// tempdir.rs
pub struct TempDir;
impl TempDir {
    pub fn new(prefix: &str) -> io::Result<Self>;
    pub fn path(&self) -> &Path;
}
// Drop removes the directory (best-effort).
```

One HTTP request per connection on both fixture servers — no keep-alive.
`fail_first(n)` drops the TCP connection with zero bytes written (a real
network-failure simulation, not a 5xx status), so retry-logic tests
exercise actual connection-error handling, not just HTTP status branching.

## Data generation (`sandbox18-datagen`)

`data/access.log` (~200k lines at `SCALE=1.0`, Combined-Log-Format-ish with
an appended response-time-ms field, Zipf-distributed path popularity
across 25 fixed literal paths, log-normal response times, ~1.5% lines
corrupted post-hoc by one of 5 corruption modes) and `data/products.csv`
(~500k rows, 12 categories Zipf-weighted, log-normal prices clamped to
[0.99, 9999.99], ~2% dirty rows via 6 corruption modes) are both written
from in-memory records; `ground-truth.json`'s aggregates are accumulated
during that same generation loop, over the *pre-corruption* well-formed/
valid records only — never by re-parsing the written text. Fixed seed
`0xC0FFEE_5EED`. All maps that get serialized to JSON are `BTreeMap`, not
`HashMap` — `HashMap`'s per-process random hasher would otherwise make two
runs of `sandbox18-datagen` produce different key order (and therefore
different bytes) in `ground-truth.json` even with an identical seed. Date
formatting is hand-rolled (Howard Hinnant's public-domain
`civil_from_days` days-since-epoch algorithm) rather than pulling in a
date/time crate, since one isn't on this module's pinned dependency list.

`SCALE` env var, default `1.0`, scales both `access.log` line count and
`products.csv` row count proportionally; the 24h/30-day time windows stay
fixed regardless of scale (higher scale = a busier day/month, not a longer
one).
