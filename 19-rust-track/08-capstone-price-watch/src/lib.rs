//! `t08-capstone-price-watch` — the module capstone.
//!
//! Three layers, wired together end to end:
//!
//! 1. **Ingest**: `fetch_price` speaks a hand-rolled HTTP/1.1 GET over
//!    `tokio::net::TcpStream` against `sandbox18_harness::async_fixture_server`,
//!    and `parse_price_payload` hand-parses the tiny fixed JSON schema each
//!    route returns (see README's "Price payload schema"). `ingest_batch`
//!    drives many of these concurrently under a hard cap enforced with
//!    `tokio::sync::Semaphore`.
//! 2. **Persistence**: `Store` is a bitcask-shaped append-only log — same
//!    on-disk idea as task 05 (framed records, an in-memory keydir, replay-
//!    based crash recovery that truncates a torn tail), reimplemented here
//!    from scratch and narrowed to this task's needs (no delete, no
//!    compaction — see README). `put_latest_price` / `get_latest_price` /
//!    `all_latest_prices` are the domain layer on top of it: they make the
//!    store hold, per product, only the record with the greatest
//!    `scraped_at` it has ever seen, regardless of the order ingest
//!    happened to observe them in.
//! 3. **Export**: `export_parquet` dumps the store's current contents
//!    (product_id, price, scraped_at) as a Parquet file via `arrow`/`parquet`.
//!
//! Every `todo!()` below is this task's actual work. Doc comments restate
//! the relevant piece of README.md's contract, but the README is the spec —
//! read it before writing code, since the on-disk format and the JSON
//! schema are both pinned exactly, not "a reasonable choice."

use std::io;
use std::path::Path;

use arrow::error::ArrowError;
use parquet::errors::ParquetError;

// =============================================================================
// Domain type
// =============================================================================

/// One price observation for one product, as ingested from a fixture route
/// and as stored/exported afterward.
#[derive(Debug, Clone, PartialEq)]
pub struct PriceRecord {
    pub product_id: String,
    pub price: f64,
    /// Logical timestamp, not wall-clock: a plain, monotonically-meaningful
    /// counter. Larger means more recent. Comparing these numerically is
    /// exactly what "freshness" means in this task — no date/time parsing
    /// involved anywhere.
    pub scraped_at: u64,
}

// =============================================================================
// JSON payload parsing
// =============================================================================

/// Every error `parse_price_payload` can produce, each carrying the byte
/// offset into the input where the problem was found (except
/// `MissingField`, which is only detectable after the whole object has been
/// consumed and something never showed up).
#[derive(Debug, Clone, PartialEq)]
pub enum ParseError {
    UnexpectedChar { pos: usize, expected: &'static str, found: char },
    UnexpectedEnd { expected: &'static str },
    InvalidNumber { pos: usize, field: &'static str },
    MissingField(&'static str),
}

impl std::fmt::Display for ParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ParseError::UnexpectedChar { pos, expected, found } => {
                write!(f, "at byte {pos}: expected {expected}, found '{found}'")
            }
            ParseError::UnexpectedEnd { expected } => {
                write!(f, "unexpected end of input, expected {expected}")
            }
            ParseError::InvalidNumber { pos, field } => {
                write!(f, "at byte {pos}: invalid number for field '{field}'")
            }
            ParseError::MissingField(name) => write!(f, "missing required field '{name}'"),
        }
    }
}

impl std::error::Error for ParseError {}

/// Hand-parses a price payload of the exact shape
/// `{"product_id": "<string>", "price": <number>, "scraped_at": <integer>}`.
///
/// This is a controlled fixture format, not general JSON, so the parser only
/// needs to handle exactly this much (see README's "Price payload schema"
/// for the full contract):
///
/// - A single flat object: no nesting, no arrays.
/// - The three fields above, in **any order**, separated by commas, each
///   `"key": value`.
/// - Whitespace (spaces only) between tokens is insignificant.
/// - `product_id`'s value is a JSON string: an ASCII-only, unescaped run of
///   characters between two `"` — no backslash escapes to handle.
/// - `price` and `scraped_at`'s values are bare JSON numbers (no quotes): an
///   optional `-`, digits, and (for `price` only) an optional `.` followed
///   by more digits. No exponent notation (`1e10`) is ever produced by this
///   task's fixtures.
///
/// No dependency on `serde_json` is used or needed here — see hint-1 for a
/// suggested parsing shape if you want it.
pub fn parse_price_payload(body: &str) -> Result<PriceRecord, ParseError> {
    let _ = body;
    todo!(
        "hand-parse the fixed {{product_id, price, scraped_at}} JSON object; \
         see README's 'Price payload schema' for the exact grammar and hint-1 \
         for a suggested parser shape"
    )
}

// =============================================================================
// Bitcask-shaped store
// =============================================================================

/// Name of the single append-only data file inside a store's directory.
pub const DATA_FILE_NAME: &str = "prices.bitcask";

/// Errors `Store`'s public API can return.
#[derive(Debug)]
pub enum StoreError {
    Io(io::Error),
    Corrupt(String),
}

impl std::fmt::Display for StoreError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            StoreError::Io(e) => write!(f, "io error: {e}"),
            StoreError::Corrupt(msg) => write!(f, "corrupt record: {msg}"),
        }
    }
}

impl std::error::Error for StoreError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            StoreError::Io(e) => Some(e),
            StoreError::Corrupt(_) => None,
        }
    }
}

impl From<io::Error> for StoreError {
    fn from(e: io::Error) -> Self {
        StoreError::Io(e)
    }
}

pub type StoreResult<T> = Result<T, StoreError>;

/// A single bitcask-style store, backed by one directory on disk.
///
/// This is the same shape as task 05's `Store` (an append-only log of
/// framed byte records plus an in-memory keydir, rebuilt by replaying the
/// log on open), narrowed for this task: no delete, no compaction — a price
/// watcher only ever learns a *newer* value for a key, it never needs to
/// remove one. See README's "On-disk format" and "Recovery" sections for
/// the exact record layout and the crash-recovery contract.
///
/// Deliberately generic over raw bytes (`&[u8]` keys, `Vec<u8>` values):
/// the price-specific encoding (how a `PriceRecord`'s `price` and
/// `scraped_at` become 16 value bytes) lives one layer up, in
/// `put_latest_price` / `get_latest_price` / `all_latest_prices` below —
/// `Store` itself knows nothing about prices.
pub struct Store {
    // Left to you: an open file/writer for appending, something to seek
    // and read for lookups, and the in-memory keydir. See hint-2.
}

impl Store {
    /// Opens (or creates) a store rooted at `dir`.
    ///
    /// `dir` must already exist. On an existing data file, replays every
    /// record from the start to rebuild the in-memory keydir. Replay stops
    /// at the first record that is truncated or fails its checksum — the
    /// store then behaves as though the file ended right before that
    /// record, and the file is truncated down to that offset before this
    /// returns, so a torn tail from a previous crash never lingers behind
    /// newly appended records. This must never return `Err` merely because
    /// the trailing bytes of the file are torn — only for a genuine I/O
    /// failure (e.g. the directory doesn't exist).
    pub fn open(dir: impl AsRef<Path>) -> StoreResult<Self> {
        let _ = dir;
        todo!(
            "replay the data file into a keydir, truncate any torn tail, \
             open for appending — see README's On-disk format/Recovery \
             sections and hint-2"
        )
    }

    /// Looks up `key` and returns its current value, or `None` if absent.
    pub fn get(&self, key: &[u8]) -> StoreResult<Option<Vec<u8>>> {
        let _ = key;
        todo!("look up key in the keydir, seek to its recorded offset, read and validate the value")
    }

    /// Inserts or overwrites `key` with `value`, appending a new record to
    /// the data file and updating the keydir to point at it.
    ///
    /// This does not, by itself, guarantee the write survives a crash —
    /// call `flush` for that (see README's "Durability").
    pub fn put(&mut self, key: Vec<u8>, value: Vec<u8>) -> StoreResult<()> {
        let _ = (key, value);
        todo!("append a framed record (checksum, key_len, value_len, key, value), update the keydir")
    }

    /// Flushes any buffered writes and syncs the data file to durable
    /// storage. After this returns `Ok`, every record appended before this
    /// call is guaranteed to survive a crash.
    pub fn flush(&mut self) -> StoreResult<()> {
        todo!("flush the writer's buffer, then sync the file to disk (see README's Durability section)")
    }

    /// Every key currently live in the store. Order is unspecified.
    pub fn keys(&self) -> Vec<Vec<u8>> {
        todo!("collect the keydir's keys")
    }

    /// Number of live keys currently in the store.
    pub fn len(&self) -> usize {
        todo!("keydir size")
    }

    /// `true` if the store currently holds no live keys.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

impl Drop for Store {
    /// Best-effort flush on close — a destructor can't return a `Result`,
    /// so this is a convenience, not a durability guarantee.
    fn drop(&mut self) {
        let _ = self.flush();
    }
}

/// Encodes `price`/`scraped_at` into this task's fixed 16-byte value layout
/// (`price` as 8 little-endian bytes, `scraped_at` as 8 little-endian
/// bytes) — the payload half of a `Store` record, once `put_latest_price`
/// has decided this record should win.
fn encode_price_value(price: f64, scraped_at: u64) -> Vec<u8> {
    let mut buf = Vec::with_capacity(16);
    buf.extend_from_slice(&price.to_le_bytes());
    buf.extend_from_slice(&scraped_at.to_le_bytes());
    buf
}

/// Decodes a value previously produced by `encode_price_value`.
fn decode_price_value(bytes: &[u8]) -> StoreResult<(f64, u64)> {
    if bytes.len() != 16 {
        return Err(StoreError::Corrupt(format!(
            "expected a 16-byte price value, got {} bytes",
            bytes.len()
        )));
    }
    let price = f64::from_le_bytes(bytes[0..8].try_into().unwrap());
    let scraped_at = u64::from_le_bytes(bytes[8..16].try_into().unwrap());
    Ok((price, scraped_at))
}

/// Writes `record` into `store` **only if** it is newer than (or there is
/// no) existing record for `record.product_id` — i.e. its `scraped_at` is
/// strictly greater than whatever is currently stored, or the key is
/// absent entirely.
///
/// Returns `Ok(true)` if the record was written (it won), `Ok(false)` if a
/// record already in the store for this product was at least as fresh (it
/// was ignored, on purpose — an ingest loop that fetches the same product
/// more than once, out of order, must never let a stale response clobber a
/// fresher one already on disk).
///
/// This is what makes ingest safe to run concurrently and out of arrival
/// order: whichever record with the greatest `scraped_at` a product has
/// ever produced is the one that survives, no matter which HTTP response
/// happened to land first.
pub fn put_latest_price(store: &mut Store, record: &PriceRecord) -> StoreResult<bool> {
    let _ = (store, record);
    todo!(
        "get() the existing value for record.product_id's key bytes, decode it if present, \
         compare scraped_at, and put() the new encoded value only if it's newer (or there \
         was nothing there yet) — see encode_price_value/decode_price_value above"
    )
}

/// Looks up the current latest-known price for `product_id`, or `None` if
/// this store has never seen that product.
pub fn get_latest_price(store: &Store, product_id: &str) -> StoreResult<Option<PriceRecord>> {
    let _ = (store, product_id);
    todo!("get() the key bytes for product_id, decode_price_value the result, wrap in a PriceRecord")
}

/// Every product currently in the store, each with its latest-known price.
/// Order is unspecified — callers that need a specific order (e.g. the
/// Parquet export) sort explicitly.
pub fn all_latest_prices(store: &Store) -> StoreResult<Vec<PriceRecord>> {
    let _ = store;
    todo!("store.keys(), then get_latest_price for each — or read the keydir + decode directly")
}

// =============================================================================
// Async ingest
// =============================================================================

/// Errors a single `fetch_price` call can produce.
#[derive(Debug)]
pub enum IngestError {
    /// The TCP connection itself could not be established or was closed
    /// before a full response arrived.
    Connect(io::Error),
    /// A connection succeeded but reading the HTTP response failed.
    Io(io::Error),
    /// A full HTTP response arrived with a non-2xx status.
    Status(u16),
    /// The response body was not a valid price payload.
    Parse(ParseError),
}

impl std::fmt::Display for IngestError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            IngestError::Connect(e) => write!(f, "connection failed: {e}"),
            IngestError::Io(e) => write!(f, "response read failed: {e}"),
            IngestError::Status(s) => write!(f, "non-2xx status: {s}"),
            IngestError::Parse(e) => write!(f, "payload parse error: {e}"),
        }
    }
}

impl std::error::Error for IngestError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            IngestError::Connect(e) | IngestError::Io(e) => Some(e),
            IngestError::Status(_) => None,
            IngestError::Parse(e) => Some(e),
        }
    }
}

impl From<ParseError> for IngestError {
    fn from(e: ParseError) -> Self {
        IngestError::Parse(e)
    }
}

/// Fetches and parses one price payload from `{base_url}{path}` (e.g.
/// `base_url = "http://127.0.0.1:53214"`, `path = "/price/widget-a"`).
///
/// Speaks exactly the HTTP subset described in README's "HTTP subset for
/// ingest": a bare `GET {path} HTTP/1.1` request with a `Host` header and
/// `Connection: close`, then a status line, a header block (only
/// `Content-Length` matters), and a body of exactly that many bytes. No
/// TLS, no chunked encoding, no redirects, no keep-alive — the fixture
/// server never exercises any of those.
pub async fn fetch_price(base_url: &str, path: &str) -> Result<PriceRecord, IngestError> {
    let _ = (base_url, path);
    todo!(
        "parse host:port out of base_url, tokio::net::TcpStream::connect, write the GET \
         request, read the status line + headers + Content-Length body, then \
         parse_price_payload the body — see hint-1 for the async I/O shape"
    )
}

/// One path's ingest outcome, as produced by `ingest_batch`.
#[derive(Debug)]
pub struct FetchAttempt {
    pub path: String,
    pub result: Result<PriceRecord, IngestError>,
}

/// Summary of one `ingest_batch` call.
#[derive(Debug)]
pub struct IngestReport {
    /// One entry per requested path, in the order each fetch *completed* —
    /// deliberately not necessarily the order `paths` was given in, since
    /// concurrent fetches under a cap finish in whatever order their
    /// (possibly delayed) responses actually arrive.
    pub attempts: Vec<FetchAttempt>,
    /// How many of the successful fetches were actually written to `store`
    /// by `put_latest_price` (i.e. were newer than what was already
    /// there). A fetch whose product was already fresher in the store
    /// counts toward `attempts` but not toward `written`.
    pub written: usize,
}

/// Fetches every path in `paths` against `base_url`, at most `concurrency_cap`
/// requests in flight at once, and writes each successfully-parsed record
/// into `store` via `put_latest_price` (so a stale, late-arriving response
/// can never clobber a fresher one already on disk).
///
/// The concurrency cap must be a hard ceiling enforced with
/// `tokio::sync::Semaphore` — never a "best effort" that merely tends to
/// stay near it. Grading observes this structurally, via the fixture
/// server's own `stats().max_concurrency`, never by timing anything.
pub async fn ingest_batch(
    base_url: &str,
    paths: &[String],
    concurrency_cap: usize,
    store: &mut Store,
) -> IngestReport {
    let _ = (base_url, paths, concurrency_cap, store);
    todo!(
        "spawn one task per path on a tokio::task::JoinSet, each acquiring an owned \
         permit from a shared Arc<Semaphore::new(concurrency_cap)> before calling \
         fetch_price, so at most concurrency_cap requests run at once; collect each \
         FetchAttempt as its task completes (NOT in `paths` order); then, back in this \
         function (not inside the spawned tasks), call put_latest_price for every \
         successful attempt and count how many actually wrote — see hint-1"
    )
}

// =============================================================================
// Parquet export
// =============================================================================

/// Errors `export_parquet` can produce.
#[derive(Debug)]
pub enum ExportError {
    Store(StoreError),
    Arrow(ArrowError),
    Parquet(ParquetError),
    Io(io::Error),
}

impl std::fmt::Display for ExportError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ExportError::Store(e) => write!(f, "store error: {e}"),
            ExportError::Arrow(e) => write!(f, "arrow error: {e}"),
            ExportError::Parquet(e) => write!(f, "parquet error: {e}"),
            ExportError::Io(e) => write!(f, "io error: {e}"),
        }
    }
}

impl std::error::Error for ExportError {}

impl From<StoreError> for ExportError {
    fn from(e: StoreError) -> Self {
        ExportError::Store(e)
    }
}

impl From<ArrowError> for ExportError {
    fn from(e: ArrowError) -> Self {
        ExportError::Arrow(e)
    }
}

impl From<ParquetError> for ExportError {
    fn from(e: ParquetError) -> Self {
        ExportError::Parquet(e)
    }
}

impl From<io::Error> for ExportError {
    fn from(e: io::Error) -> Self {
        ExportError::Io(e)
    }
}

/// Dumps every product currently in `store` to a Parquet file at
/// `out_path`, with columns `product_id: Utf8`, `price: Float64`,
/// `scraped_at: UInt64` — one row per product, its current latest-known
/// price. Returns the number of rows written.
///
/// Row order in the output is unspecified; grading reads the file back and
/// compares per-product values, never positional rows.
pub fn export_parquet(store: &Store, out_path: impl AsRef<Path>) -> Result<usize, ExportError> {
    let _ = (store, out_path);
    todo!(
        "all_latest_prices(store), build a 3-column RecordBatch (StringArray, \
         Float64Array, UInt64Array) over an arrow Schema, open out_path as a \
         std::fs::File, wrap it in parquet::arrow::ArrowWriter::try_new, write() the \
         batch, close() the writer — see hint-3"
    )
}
