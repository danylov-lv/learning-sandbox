# 04 -- URL Health Checker

## Backstory

The crawler fleet from your day job just grew from a few dozen target
endpoints to a few thousand. Someone still needs to know, on a schedule:
which of them are up, which are returning errors, which are flapping
(fail sometimes, succeed other times), and which have gone dark entirely.
Checking them one at a time, sequentially, would take the whole scheduling
window before the answer was even useful -- by the time you'd checked
endpoint #3000, the answer for endpoint #1 might already be stale.

This is a small systems problem wearing a data-engineering costume: you
need a bounded pool of workers pulling from a shared queue, a way to get
results back to one place safely, and a hard ceiling on how many requests
are ever in flight at once (a target host that gets hammered by three
thousand simultaneous connections is not "healthy" -- it just went down a
second way). No `tokio` here on purpose: `std::thread`, `mpsc`, and
`Arc<Mutex<..>>`/atomics are the whole toolbox. Async shows up in task 07,
once this synchronous mental model -- what a thread pool actually is, what
a channel actually does -- is solid.

## What's given

- `src/lib.rs` -- a scaffold: the `CheckOutcome` and `HealthReport` types
  (fully defined, not stubs -- these are the shared vocabulary your code
  and the tests both speak), the `Checker` trait, an `HttpChecker` struct
  with `todo!()` bodies, and the `check_urls_concurrently` pool-runner
  function signature, also `todo!()`.
- `src/main.rs` -- an optional, ungraded CLI stub.
- `sandbox18_harness::fixture_server` (a dependency, not something you
  write): a blocking HTTP/1.1 server on an ephemeral `127.0.0.1` port with
  per-route status/body/delay/`fail_first(n)` behavior, plus a
  `stats()` call exposing total requests observed and the actual
  max *observed* concurrency at the server, both tracked independently of
  your code. `tests/` uses it; you can build your own instance of it too
  while experimenting (see any given test for the builder pattern).
- `tests/` -- the validator. Every test's assertions carry an explanatory
  message.

## What's required

Implement the three `todo!()` pieces in `src/lib.rs`:

1. **`HttpChecker::new`** -- store the three fields.
2. **`impl Checker for HttpChecker`** -- a hand-rolled HTTP/1.1 GET client
   over `std::net::TcpStream` (see "The HTTP subset" below), with
   connect/read timeouts and the retry contract (see "Retry contract"
   below), classified into a `CheckOutcome`.
3. **`check_urls_concurrently`** -- a fixed pool of `worker_count` threads
   pulling from one shared work queue over `urls`, each calling
   `checker.check(url)` and sending a `HealthReport` back through an
   `mpsc` channel, collected into the returned `Vec`.

### The URL format

Every URL your `HttpChecker` needs to handle looks like
`http://127.0.0.1:PORT/path` (the fixture server's `base_url()` plus a
route path) -- parse out the host, the port, and the path yourself. No
query strings, no fragments, no userinfo. `https://` is never used
anywhere in this task; you do not need to detect or reject it.

### The HTTP subset (exactly this, nothing more)

**Request**, written by you over a plain `TcpStream`:

```
GET {path} HTTP/1.1\r\n
Host: {host}:{port}\r\n
Connection: close\r\n
\r\n
```

**Response**, read and parsed by you:

- A status line (`HTTP/1.1 200 OK`) -- you need the numeric status code
  out of it, nothing else from that line.
- Headers, one per line, terminated by an empty line (`\r\n\r\n` overall).
  You only need to find and parse `Content-Length` (case-insensitively);
  every other header can be read and discarded.
- A body of exactly `Content-Length` bytes, if the header was present. You
  do not need to inspect the body's contents for this task -- only its
  presence/length matters for correctly finishing the read.

Explicitly **not required, and never exercised by the fixture server**:
chunked transfer encoding, TLS/HTTPS, redirects (3xx is just another
non-2xx status to classify as `Unhealthy`), keep-alive / multiple requests
per connection (`Connection: close` is honest -- the server closes after
one response, and so should your client).

### Timeouts

- `HttpChecker.connect_timeout` bounds `TcpStream::connect_timeout` for
  the initial TCP handshake.
- `HttpChecker.read_timeout` bounds every read from the socket via
  `set_read_timeout` -- applied before you start reading the status line,
  and it must still apply while reading the body.
- If a read exceeds `read_timeout` (or connect exceeds `connect_timeout`
  and doesn't count as a connection failure below -- see next section),
  classify the outcome as `CheckOutcome::Timeout` and stop: **do not
  retry a timeout.** A slow-but-alive server is a different failure mode
  than a dead one, and retrying it just piles up more in-flight requests
  against an already-slow endpoint.

### Retry contract

`HttpChecker.max_retries` bounds retries for exactly one failure class:
**connection-level failure** -- either `TcpStream::connect` itself fails
(e.g. connection refused, nobody listening on that port), or the
connection is accepted but closes with zero bytes read before a full
status line arrives (this is exactly what the fixture server's
`fail_first(n)` routes do: they accept the TCP connection, then drop it
immediately with no bytes written, simulating a real network failure
rather than an HTTP-level error).

- On a connection-level failure, retry immediately (no backoff -- that's
  task 07's concern once async is in the picture) up to `max_retries`
  additional times. Total attempt budget is `1 + max_retries`.
- If an attempt within that budget succeeds (a full HTTP response is
  read), classify normally (`Healthy`/`Unhealthy`) with `attempts` set to
  however many attempts it actually took.
- If every attempt in the budget fails at the connection level,
  `CheckOutcome::ConnectionFailed { attempts }` with `attempts == 1 +
  max_retries`.
- A non-2xx HTTP response (404, 500, ...) is **not** a connection failure
  and is never retried -- the server answered, it just didn't answer
  "OK". Classify it `Unhealthy` immediately, `attempts: 1`.
- A `Timeout` is never retried (see above) -- it's the one variant with no
  `attempts` field, always exactly one attempt.

### The concurrency cap

`check_urls_concurrently`'s `worker_count` parameter is a hard ceiling:
at no instant may more than `worker_count` calls to `checker.check` be
executing concurrently, regardless of how many URLs are queued. This is
graded structurally against the fixture server's own `stats().
max_concurrency` counter (tracked independently, inside the server, via
its own atomics) -- never against wall-clock elapsed time. A pool that
just spawns one thread per URL with no cap fails this the moment there
are more URLs than the cap; a pool that processes URLs one at a time
(no real concurrency at all) fails the companion assertion that
concurrency actually *reaches* the cap when there's enough work to fill
it.

## Completion criteria

```bash
cd 18-rust-track
cargo test -p t04-url-health-checker
```

All given tests pass. They cover, at minimum:

- A `200 OK` route classifies `Healthy`.
- `404` and `500` routes both classify `Unhealthy` with the right status
  each.
- A `fail_first(n)` route eventually classifies `Healthy` with `attempts`
  matching the retry contract, given enough `max_retries` budget.
- A connection to a closed port (nobody listening) classifies
  `ConnectionFailed` after exhausting the retry budget.
- A route delayed past `read_timeout` classifies `Timeout`.
- The pool's observed concurrency, measured by the fixture server itself,
  never exceeds the configured cap, and does reach it when there's more
  work than the cap against a delayed route.
- A fake, in-test `Checker` (no sockets) proves the pool's result
  aggregation and classification handling independent of any of the above.

## Estimated evenings

1-2

## Topics to read up on

- The HTTP/1.1 request/response format at the byte level -- request line,
  header block, `Content-Length`-delimited body
- `std::net::TcpStream::connect_timeout` vs. a plain `connect` (why the
  latter has no timeout at all on some platforms)
- `set_read_timeout` / `set_write_timeout` and how a timed-out read
  surfaces as an `io::Error` (which `ErrorKind`, exactly)
- Worker-pool patterns over a shared queue: `Arc<Mutex<VecDeque<T>>>` vs.
  an atomic index into a shared slice -- trade-offs of each
- `std::thread::scope` vs. `thread::spawn` + `JoinHandle::join` -- what
  the scoped variant buys you when your closures borrow data instead of
  owning it
- `mpsc::channel` / `Sender::clone` -- why cloning the sender per worker
  and dropping each clone at the end of its thread is what lets a
  `Receiver` know "no more messages are coming" without an explicit count
- `Send` and `Sync` -- what each one actually promises, and why a trait
  used across threads needs both as supertraits
- TCP connection refused vs. connection reset vs. read timeout -- three
  different failure shapes with three different causes, all easy to
  conflate if you only match on "did the read fail"

## Off-limits

`.authoring/design.md` (at the module root) documents this task's grading
internals -- read it after you're done, if at all, not before.
