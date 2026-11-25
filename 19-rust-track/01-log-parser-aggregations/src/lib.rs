//! Parses `data/access.log` — a Combined-Log-Format-ish web/scraper access
//! log with an appended response-time-ms field — and reproduces the
//! aggregates checked against `data/ground-truth.json`.
//!
//! ## Line format
//!
//! Each well-formed line looks like:
//!
//! ```text
//! 108.204.108.63 - - [01/Jan/2024:00:00:02 +0000] "GET /api/products HTTP/1.1" 200 60258 "-" "Mozilla/5.0 (compatible; sandbox18-bot/1.0)" 18.4
//! ```
//!
//! Fields, in order: client IP, two `-` placeholders (ident, authuser —
//! always `-` here, not otherwise meaningful), a `[...]`-bracketed
//! timestamp, a `"..."`-quoted request line (`METHOD PATH HTTP/1.1`), an
//! HTTP status code, a response size in bytes, a `"-"` referrer
//! placeholder, a `"..."`-quoted user-agent string, and finally a bare
//! response time in milliseconds (one decimal place in the source data,
//! but parse it as `f64`).
//!
//! About 1.5% of lines in the real file are corrupted (missing brackets,
//! a non-numeric status, a truncated line, stripped quotes, or a trailing
//! garbage token) — `parse_line` must report those as `Err`, never panic
//! or silently guess a value.
//!
//! ## What must not allocate
//!
//! [`LogEntry`] borrows every string field from the input line (`ip`,
//! `timestamp`, `method`, `path` are all `&str` slices of the line you
//! were given, not owned `String`s). This isn't just a style preference:
//! the struct's lifetime parameter makes it a compile error to hand back
//! anything that isn't a borrow of the input, so there's no way to satisfy
//! the type checker by allocating a `String` per field and calling it
//! done.
//!
//! ## A trap worth knowing about up front
//!
//! Don't accept the IP field just because "there's text before the first
//! space." One of the corruption modes in the real data overwrites the
//! *first* occurrence of the status-code digits anywhere in the line with
//! a placeholder — and since IPs are digit-heavy, that occasionally lands
//! inside the IP octets instead of the actual status field, leaving an
//! otherwise-untouched (and therefore superficially parseable) line with
//! garbage where an octet should be. The ground truth still treats that
//! record as malformed. If your parser doesn't check that the IP field
//! actually *looks like* an IP (four dot-separated groups of digits), it
//! will accept a couple of these by accident, and your full-corpus counts
//! will come out a handful off from `ground-truth.json` — the kind of
//! near-miss that's miserable to debug from aggregate counts alone.

use std::collections::HashMap;
use std::fmt;
use std::io::BufRead;
use std::num::{ParseFloatError, ParseIntError};

/// One parsed access-log entry, borrowing every string field from the
/// input line.
#[derive(Debug, Clone, PartialEq)]
pub struct LogEntry<'a> {
    pub ip: &'a str,
    /// Raw text between the `[` and `]`, e.g. `"01/Jan/2024:00:00:02 +0000"`.
    pub timestamp: &'a str,
    pub method: &'a str,
    pub path: &'a str,
    pub status: u16,
    pub bytes: u64,
    pub response_time_ms: f64,
}

/// Everything that can go wrong parsing one line. Implements
/// [`std::error::Error`] + [`Display`](fmt::Display) so it composes with
/// `?` and with anything else in the ecosystem that expects a standard
/// error trait object.
#[derive(Debug)]
pub enum LogParseError {
    /// A required section of the line (bracketed timestamp, quoted
    /// request, quoted user-agent, or a plain field) was not where the
    /// format says it should be. Carries a short human-readable label for
    /// what was expected.
    MissingField(&'static str),
    /// The status-code or byte-count field did not parse as an integer.
    InvalidInteger(ParseIntError),
    /// The response-time-ms field did not parse as a float.
    InvalidFloat(ParseFloatError),
}

impl fmt::Display for LogParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        todo!("write a message identifying which field/section failed and why")
    }
}

impl std::error::Error for LogParseError {}

impl From<ParseIntError> for LogParseError {
    fn from(err: ParseIntError) -> Self {
        todo!("wrap `err` in the right LogParseError variant")
    }
}

impl From<ParseFloatError> for LogParseError {
    fn from(err: ParseFloatError) -> Self {
        todo!("wrap `err` in the right LogParseError variant")
    }
}

/// Parses one line of `access.log` into a [`LogEntry`], borrowing all
/// string fields from `line`.
///
/// Returns `Err(LogParseError)` for anything that doesn't match the format
/// described in the module docs above — never panics, never returns a
/// partially-filled or best-guess `LogEntry`. In particular, validate that
/// the IP field actually looks like an IP (see the module docs' "trap"
/// section) rather than accepting whatever text precedes the first space.
pub fn parse_line(line: &str) -> Result<LogEntry<'_>, LogParseError> {
    todo!("split `line` into its fields and build a LogEntry, propagating parse failures with `?`")
}

/// Which status class (`"2xx"`..`"5xx"`) a status code belongs to.
pub fn status_class(status: u16) -> String {
    todo!("e.g. 404 -> \"4xx\"")
}

/// Response-time percentile statistics, all in milliseconds.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct ResponseTimeStats {
    pub mean_ms: f64,
    pub p50_ms: f64,
    pub p95_ms: f64,
    pub p99_ms: f64,
    pub max_ms: f64,
}

/// Aggregates computed over the well-formed lines of a log stream.
/// Malformed lines are counted in `malformed_lines` but do not otherwise
/// contribute to any field below.
#[derive(Debug, Clone, Default)]
pub struct LogStats {
    pub total_lines: u64,
    pub well_formed_lines: u64,
    pub malformed_lines: u64,
    /// Keyed by `"2xx"`.."5xx"`.
    pub status_class_counts: HashMap<String, u64>,
    pub method_counts: HashMap<String, u64>,
    /// Full per-path request histogram.
    pub path_counts: HashMap<String, u64>,
    /// Count of distinct client IPs seen among well-formed lines.
    pub unique_ips: usize,
    /// Fraction (0.0..=1.0) of well-formed lines with a 5xx status.
    pub error_rate_5xx: f64,
    pub response_time_stats: ResponseTimeStats,
}

/// Streams `reader` line by line — via [`BufRead::lines`], never by
/// reading the whole input into one `String` — parsing each line with
/// [`parse_line`] and folding the results into a [`LogStats`].
///
/// A line that fails to parse increments `malformed_lines` and is
/// otherwise excluded from every aggregate; it must never be dropped
/// without being counted, and it must never panic the whole aggregation.
pub fn aggregate<R: BufRead>(reader: R) -> LogStats {
    todo!("reader.lines() -> parse_line each -> fold into LogStats, using percentile() for response_time_stats")
}

/// The value at percentile `p` (in `[0.0, 1.0]`) of `sorted_ascending`,
/// using the nearest-rank method: the value at index
/// `round(p * (len - 1))` of the ascending-sorted slice. This is the exact
/// definition `sandbox18-datagen` used to compute the ground-truth
/// percentiles — a different interpolation scheme (e.g. linear
/// interpolation between ranks) will not match them.
///
/// Returns `0.0` for an empty slice.
pub fn percentile(sorted_ascending: &[f64], p: f64) -> f64 {
    todo!()
}

/// Top `n` paths by request count, descending; ties broken by path name
/// ascending. Matches the ordering rule `ground-truth.json`'s `top_paths`
/// was built with.
pub fn top_paths(path_counts: &HashMap<String, u64>, n: usize) -> Vec<(String, u64)> {
    todo!()
}
