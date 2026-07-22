# 08 — Capstone: Price Watch

## Backstory

Every earlier task in this track solved one problem in isolation: parse a
log, evaluate an expression, write a Parquet file, check a batch of URLs,
persist key-value pairs durably, render a dashboard, fetch concurrently
under a cap. A real price-watching service needs all of that at once, and
in the right order: poll a fleet of upstream endpoints for the current
price of every product you care about, without letting slow endpoints
choke out fast ones; remember what you learned somewhere that survives the
process dying mid-write, because a price watcher that forgets everything
on every restart is useless; and periodically hand off a snapshot of
"what do we currently believe the price of everything is" to whatever
downstream system (a dashboard, an alerting job, an analyst's notebook)
wants to read it in bulk, in a columnar format, not by replaying a log.

This capstone is exactly that pipeline, at a scale small enough to build
and test in a few evenings: **ingest** (poll a fixture server standing in
for the upstream price feeds, under a hard concurrency cap) → **persist**
(a bitcask-shaped append-only log, same idea as task 05, rebuilt from
scratch in this crate) → **export** (dump the current state to Parquet via
`arrow`/`parquet`). It reuses the idioms from tasks 05 and 07 directly —
if either of those isn't solid yet, this is a good excuse to revisit them
first.

## What's given

- `src/lib.rs` — the scaffold: `PriceRecord` (fully defined — the shared
  vocabulary), the `ParseError`/`StoreError`/`IngestError`/`ExportError`
  enums with `Display`/`std::error::Error`/`From` impls already wired
  (ordinary plumbing, not the lesson), and every function/method that *is*
  the lesson ending in `todo!()` with a doc comment restating this
  README's contract for it.
- `src/main.rs` — an optional, ungraded demo binary that wires ingest →
  store → export together against an in-process fixture server. `cargo
  test` never runs it; it exists purely so you have something to run by
  hand once the pieces work.
- `Cargo.toml` — already has `tokio`, `arrow`, `parquet`, and
  `sandbox18-harness` (with its `async` feature) wired as dependencies,
  plus `tempfile` as a dev-dependency for the tests' scratch directories.
- `tests/` — the GIVEN validator, three checkpoints. Do not weaken or
  remove assertions here; see "Completion criteria."

## What's required

Three layers. Build and test them roughly in this order — each is usable
on its own before the next depends on it.

### 1. The price payload schema (parsing)

Every route this task's tests configure on the fixture server returns a
body of exactly this shape:

```json
{"product_id": "widget-a", "price": 19.99, "scraped_at": 1000}
```

- A single flat JSON object — no nesting, no arrays.
- The three fields above, in **any order**, comma-separated.
- Whitespace (plain spaces) around punctuation is insignificant.
- `product_id`'s value is a JSON string: a `"`-delimited, ASCII-only,
  unescaped run of characters — no backslash escapes ever appear in this
  task's fixtures, so you don't need to handle them.
- `price`'s value is a bare (unquoted) JSON number: an optional leading
  `-`, digits, optionally a `.` followed by more digits. Never an
  exponent (`1e10`).
- `scraped_at`'s value is a bare non-negative integer — a **logical**
  timestamp, not a wall-clock one. Larger means more recently observed;
  nothing in this task ever parses it as a date. Comparing two
  `scraped_at` values numerically is the entire definition of "which one
  is fresher" everywhere in this task.

`parse_price_payload(body: &str) -> Result<PriceRecord, ParseError>` is a
hand-rolled parser for exactly this grammar — no `serde_json` dependency
exists in this crate on purpose. `ParseError` carries the byte offset of
whatever went wrong, in the same spirit as task 02's expression parser
errors.

### 2. The bitcask-shaped store (persistence)

`Store` is a directory-backed, append-only log — the same architecture as
task 05's `Store` (not imported from it — every task crate in this module
stands alone — reimplemented here from scratch), narrowed to exactly what
a price watcher needs: no delete, no tombstones, no compaction. A price
watcher only ever learns a *newer* value for a key; it never needs to
forget one.

#### On-disk format

A store is a directory. Inside it, exactly one file matters:
`DATA_FILE_NAME` (`"prices.bitcask"`, exported as a constant so tests can
find and directly truncate it).

That file is an append-only sequence of **records**, every one with this
exact byte layout, all multi-byte integers little-endian:

```
byte offset   field          size      meaning
-----------   -----          ----      -------
0             checksum       4 bytes   u32, FNV-1a, see below
4             key_len        4 bytes   u32, length of key in bytes
8             value_len      4 bytes   u32, length of value in bytes
12            key bytes      key_len   raw key bytes (UTF-8 product_id)
12+key_len    value bytes    value_len raw value bytes
```

So a record is `12 + key_len + value_len` bytes on disk. There is no
tombstone sentinel in this task's format — every record is a live value.

**Checksum**: FNV-1a, 32-bit, computed over every byte of the record
*except* the checksum field itself (`key_len_le ++ value_len_le ++
key_bytes ++ value_bytes`):

```rust
fn fnv1a32(data: &[u8]) -> u32 {
    let mut hash: u32 = 0x811c_9dc5;
    for &b in data {
        hash ^= b as u32;
        hash = hash.wrapping_mul(0x0100_0193);
    }
    hash
}
```

This is pinned exactly, same reasoning as task 05: it covers the length
fields too, so a torn write that corrupts `key_len` or `value_len` (not
just the payload) is still caught during replay.

#### The keydir

An in-memory index mapping each key currently in the store to where its
value lives on disk: `key: Vec<u8> -> (value_offset: u64, value_len: u32)`
(no `file_id` in this task — there's only ever one data file, and no
compaction that would ever create a second one).

#### Recovery (replay on open)

`Store::open` reads `DATA_FILE_NAME` from the start, one record at a
time, rebuilding the keydir — **identical rules to task 05**:

1. Read 12 bytes for the header. Exactly 0 bytes read at a record
   boundary is a clean EOF — replay is done, no error.
2. A short read (1–11 bytes) is a **torn header** — stop replay here, not
   an error.
3. Read `key_len` bytes for the key, then `value_len` bytes for the
   value. A short read at either step is a **torn record** — same
   handling.
4. Recompute the checksum over the bytes just read; a mismatch is
   treated exactly like a torn record.
5. On a valid record: insert/overwrite `key -> (value_offset, value_len)`
   in the keydir, advance to the next record.

**Replay stops at the first record that doesn't fully and correctly
parse, and everything before that point is kept** — never fewer records
than were validly written, never a corrupted/partial record accepted.
`Store::open` returns `Err` only for a genuine I/O failure, never merely
because the file's tail is torn.

After replay stops, **truncate the data file down to exactly the offset
where replay stopped**, before returning from `open` — otherwise a torn
tail from a previous crash sits as garbage between the last good record
and newly appended ones, and the *next* recovery pass would stop there
instead of reading past it.

#### Durability

Same contract as task 05: a `put` is not guaranteed to survive a crash
until `flush` is called (`flush` must flush the buffered writer *and*
sync the file — `File::sync_data`/`sync_all`; either alone is not
enough). `get` must always return the most recently `put` value for a key
in the same process, even without an intervening `flush` — read-your-own-
writes correctness is independent of the crash-durability guarantee. If
your very first put-then-get fails with an unexpected-EOF-shaped error,
see task 05's README (or hint-2 here) for why: flush the writer's own
buffer unconditionally after every `put`, reserve the expensive
`sync_all` exclusively for the public `flush` method.

`Drop` calls `flush` best-effort, same as task 05 — not a substitute for
calling it explicitly wherever the guarantee actually matters.

### 3. Latest-price-wins (the domain layer over `Store`)

`Store` itself is byte-generic — it has no idea what a price is. Three
free functions sit on top of it and give it price semantics:

- `put_latest_price(store, record)` — writes `record` **only if** its
  `scraped_at` is strictly greater than whatever is already stored for
  `record.product_id` (or nothing is stored yet). Returns whether it
  actually wrote. This is the one piece of logic that makes concurrent,
  out-of-order ingest safe: whichever observation of a product has the
  greatest `scraped_at` survives, no matter which HTTP response happened
  to land first.
- `get_latest_price(store, product_id)` — the current latest-known
  record for one product, or `None`.
- `all_latest_prices(store)` — every product currently known, each with
  its latest-known record.

A `price`/`scraped_at` pair is encoded as exactly 16 bytes (`price` as 8
little-endian bytes, `scraped_at` as 8 little-endian bytes) — this is the
value half of a `Store` record; `encode_price_value`/`decode_price_value`
in `src/lib.rs` already do this encoding for you, `put_latest_price` and
friends just need to call them.

### 4. Async ingest, under a hard concurrency cap

`fetch_price(base_url, path)` speaks a hand-rolled HTTP/1.1 GET over
`tokio::net::TcpStream` — the async counterpart of task 04's synchronous
client, against `sandbox18_harness::async_fixture_server` instead of the
blocking one. The HTTP subset is exactly task 04's, nothing more:

```
GET {path} HTTP/1.1\r\n
Host: {host}:{port}\r\n
Connection: close\r\n
\r\n
```

read a status line, a header block (only `Content-Length` matters,
case-insensitively), and a body of exactly that many bytes. No TLS, no
chunked encoding, no redirects, no keep-alive.

`ingest_batch(base_url, paths, concurrency_cap, store)` fetches every
path in `paths`, **at most `concurrency_cap` requests in flight at any
instant**, and writes every successfully-parsed record into `store` via
`put_latest_price`. The cap is a hard ceiling enforced with
`tokio::sync::Semaphore` (an owned permit per in-flight fetch, acquired
before the request starts and dropped when it finishes) — not "a pool
that tends to stay near it." Grading checks this **structurally**,
against the fixture server's own `stats().max_concurrency` counter
(tracked independently, inside the server) — never by measuring elapsed
wall-clock time. It also checks that concurrency actually *reaches* the
cap when there's more work than the cap against delayed routes — a
sequential "one fetch at a time" implementation fails that half just as
surely as an uncapped one fails the ceiling half.

`IngestReport::attempts` is in **completion order**, not `paths` order —
under real concurrency, whichever request's response arrives first
finishes first, regardless of which path was listed first. Anything that
consumes `attempts` and expects input order is already assuming away the
concurrency this function is required to have.

### 5. Parquet export

`export_parquet(store, out_path)` dumps `all_latest_prices(store)` as a
three-column Parquet file: `product_id: Utf8`, `price: Float64`,
`scraped_at: UInt64`, one row per product. Build a `RecordBatch` over an
explicit `arrow::datatypes::Schema`, write it with
`parquet::arrow::ArrowWriter`, and `close()` the writer (which flushes
the file's footer — a Parquet file with no footer isn't a valid Parquet
file at all, regardless of how correct the row data is). Row order in the
file is unspecified; grading reads it back and compares per-product
values, never positional rows.

## Completion criteria

```bash
cd 18-rust-track
cargo test -p t08-capstone-price-watch            # all three checkpoints
cargo test -p t08-capstone-price-watch --test cp1  # one checkpoint at a time
cargo test -p t08-capstone-price-watch --test cp2
cargo test -p t08-capstone-price-watch --test cp3
```

- **CP1** (`tests/cp1.rs`) — ingest + bitcask persistence. Starts an
  `AsyncFixtureServer` serving a large, deliberately-varied set of known
  price payloads (distinct product ids, distinct prices, distinct
  `scraped_at` values, and enough of them that a naive fixed-size buffer
  wouldn't survive writing them all before a flush), runs `ingest_batch`
  into a fresh `tempfile` store, and checks the store's final contents
  against that known set exactly — count and per-product price, compared
  against the test's own hardcoded expectations, never the store's own
  second opinion of itself. Separately, it prepares a store directly via
  `put_latest_price` (no network involved), truncates the data file
  mid-record through a raw file handle (bypassing `Store` entirely, the
  same technique as task 05's crash-recovery test), reopens it, and
  asserts that exactly the fully-flushed records survive — never fewer,
  never a corrupted partial record accepted.
- **CP2** (`tests/cp2.rs`) — adds the Parquet export and an end-to-end
  freshness check. Ingests a set of products where several have more than
  one observation at different (fixture-configured) delays and different
  `scraped_at` values — some earlier than the product's "real" price,
  some later — so that only comparing `scraped_at` (not arrival order,
  not which route happened to be listed first) picks the right winner.
  Exports to a tempfile, reads it back with
  `parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder`, and
  asserts row count, per-product price, and that every exported row's
  `scraped_at` really is the maximum ever observed for that product.
- **CP3** (`tests/cp3.rs`) — adds the concurrency-cap and crash-recovery-
  under-ingest checks, and re-runs CP1's and CP2's checks (via shared
  helpers in `tests/common/mod.rs`) so a regression introduced while
  building CP3 doesn't slip through. The concurrency cap is asserted
  purely structurally (`server.stats().await.max_concurrency <= cap`,
  and a companion assertion that it also *reaches* the cap given enough
  delayed routes). Crash recovery under ingest: ingest half a known set,
  flush, truncate the log directly to simulate a crash, reopen (recovery
  runs), ingest the **full** set again (resume), and assert the final
  state is exactly the full expected set — proving `put_latest_price`'s
  idempotent, order-independent design converges correctly even after a
  crash truncated whatever was mid-flight. CP3 also gates an unfilled
  `DESIGN.md`: fill in every `## ` section with real analysis grounded in
  what you actually built (see the template) before CP3 passes.

Every assertion in the given tests carries a message explaining what it
means if it fails.

## Estimated evenings

3-5

## Topics to read up on

- Task 05's bitcask design (keydir, append-only log, replay-based
  recovery) and task 04/07's concurrency-cap pattern (worker pool /
  semaphore-bounded fan-out) — this capstone is those two ideas
  combined, not a new one
- `tokio::sync::Semaphore` and `acquire_owned` — why an *owned* permit
  (not a borrowed one) is what lets a spawned task hold it for its whole
  lifetime without fighting the borrow checker
- `tokio::task::JoinSet` — spawning a dynamic number of same-shaped
  tasks and collecting their results as they complete, rather than in
  submission order
- `arrow::record_batch::RecordBatch` / `ArrayBuilder`s (or building
  arrays directly from `Vec`s via `From`) and
  `parquet::arrow::ArrowWriter` — the write path task 03 also exercises
- `parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder` — the
  read-back path, used here by the tests, not by your own code
- Idempotency and convergence: why "apply the newest observation, ignore
  anything older" makes an ingest loop safe to run concurrently, safe to
  retry, and safe to resume after a crash, all for the same reason
- `File::sync_all`/`sync_data` and why a `BufWriter::flush()` alone is
  not a durability guarantee (task 05's README goes into this in more
  depth)

## Off-limits

`.authoring/design.md` (at the module root) documents this task's
grading internals and idiom checklist — spoilers. Read it after you've
finished, if at all, same rule as every other task in this module.
