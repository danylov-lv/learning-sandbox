//! t04-url-health-checker.
//!
//! A multithreaded URL health checker: a fixed-size worker pool checks a
//! batch of URLs concurrently under a hard cap on in-flight requests, using
//! a hand-rolled HTTP/1.1 GET over `std::net::TcpStream` -- no HTTP client
//! crate, no async. See README.md for the exact HTTP subset required, the
//! retry contract, and the concurrency/timeout contract this crate must
//! satisfy; the `tests/` directory is the validator.

use std::time::Duration;

/// The result of checking a single URL, including how many attempts it
/// took to reach that result.
///
/// `Timeout` has no `attempts` field: a read-timeout is reported and
/// surfaced immediately, never retried (see README's retry contract for
/// why). The other three variants always carry the number of attempts
/// actually made, so a test can assert both the classification and the
/// retry count against `fail_first(n)` / connection-refused routes without
/// depending on wall-clock timing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CheckOutcome {
    /// A full HTTP response arrived with a 2xx status.
    Healthy { status: u16, attempts: u32 },
    /// A full HTTP response arrived with a non-2xx status (e.g. 404, 500).
    Unhealthy { status: u16, attempts: u32 },
    /// Every attempt failed at the connection level: refused at connect
    /// time, or the connection closed with zero bytes before a full
    /// response was read.
    ConnectionFailed { attempts: u32 },
    /// The connection was established but no full response arrived before
    /// the configured read timeout elapsed.
    Timeout,
}

impl CheckOutcome {
    /// Number of attempts this outcome represents (`Timeout` is always 1 --
    /// it is a terminal, non-retried outcome).
    pub fn attempts(&self) -> u32 {
        match self {
            CheckOutcome::Healthy { attempts, .. }
            | CheckOutcome::Unhealthy { attempts, .. }
            | CheckOutcome::ConnectionFailed { attempts } => *attempts,
            CheckOutcome::Timeout => 1,
        }
    }

    /// True only for `Healthy`. Convenience for aggregation over a batch of
    /// reports; deliberately not `true` for `Unhealthy` -- a 404/500 is a
    /// real answer from a real server, not a healthy one.
    pub fn is_healthy(&self) -> bool {
        matches!(self, CheckOutcome::Healthy { .. })
    }
}

/// One URL's result, as collected back from the worker pool.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HealthReport {
    pub url: String,
    pub outcome: CheckOutcome,
}

/// The injectable checking strategy. `HttpChecker` is the real
/// implementation; tests provide a fake (deterministic, no sockets) to
/// prove the pool's classification, aggregation, and error handling
/// without touching the network.
///
/// `Send + Sync` supertraits: instances of this trait get shared across
/// worker threads by reference, so any implementation must tolerate being
/// called concurrently from multiple threads.
pub trait Checker: Send + Sync {
    fn check(&self, url: &str) -> CheckOutcome;
}

/// A hand-rolled HTTP/1.1 GET client over `std::net::TcpStream`.
///
/// See README.md for:
/// - the exact HTTP subset this must speak (request line, `Host` header,
///   status line + headers + body, `Content-Length`, no chunked encoding,
///   no TLS, no redirects),
/// - the exact retry contract (which outcomes retry, which don't, and how
///   `max_retries` bounds the attempt budget).
pub struct HttpChecker {
    pub connect_timeout: Duration,
    pub read_timeout: Duration,
    pub max_retries: u32,
}

impl HttpChecker {
    pub fn new(connect_timeout: Duration, read_timeout: Duration, max_retries: u32) -> Self {
        todo!("store the three fields on Self")
    }
}

impl Checker for HttpChecker {
    fn check(&self, url: &str) -> CheckOutcome {
        todo!(
            "parse `url` into host, port, path; attempt a GET with connect/read timeouts; \
             on a connection-level failure, retry per the README's contract up to \
             self.max_retries; classify the eventual result into a CheckOutcome variant"
        )
    }
}

/// Checks every URL in `urls` using a fixed pool of `worker_count` threads
/// pulling from one shared work queue, collecting results through an mpsc
/// channel.
///
/// `worker_count` is a HARD CAP on concurrent in-flight requests: at most
/// `worker_count` calls to `checker.check` may be in progress at any
/// instant, no matter how many URLs are queued. See README.md for exactly
/// how this is graded (structurally, against the fixture server's own
/// observed-concurrency counter -- never against wall-clock elapsed time).
///
/// The returned `Vec`'s order is NOT guaranteed to match `urls`' order --
/// results are collected as workers finish, not in submission order.
pub fn check_urls_concurrently<C>(
    checker: &C,
    urls: &[String],
    worker_count: usize,
) -> Vec<HealthReport>
where
    C: Checker + ?Sized,
{
    todo!(
        "spin up worker_count threads (thread::scope or spawn+join) sharing a work queue \
         (Arc<Mutex<_>> and/or an atomic index over `urls`), have each worker call \
         checker.check and send a HealthReport back through an mpsc channel, then collect \
         all of them on the way out"
    )
}
