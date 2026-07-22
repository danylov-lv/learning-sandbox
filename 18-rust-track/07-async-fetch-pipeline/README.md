# 07 -- Async Fetch Pipeline

## Backstory

Task 04 built the synchronous mental model: a fixed pool of threads, a
shared queue, a channel carrying results back to one place, a hard cap on
in-flight work. That model works, but it doesn't scale past a few hundred
threads, and it has nowhere to put "please stop now, cleanly" short of
letting every thread finish whatever it's doing. This task rebuilds the
same problem -- fetch a batch of URLs under a concurrency cap, with
retries and timeouts -- on `tokio` instead, and adds the two things a
thread pool can't give you cheaply: a *bounded* channel that actually
backpressures the producer side instead of just buffering forever, and a
cooperative shutdown signal that every in-flight unit of work can observe
and honor without anyone calling `abort()` on anything.

No HTTP client crate here either, on purpose -- the hand-rolled HTTP/1.1
parsing from task 04 ports over almost unchanged, just async. What's new
is retry-with-*backoff* (04 retried immediately; a slow failing endpoint
deserves a growing pause between attempts, not a hot loop hammering it),
and everything tokio: `Semaphore`, `JoinSet`, bounded `mpsc`, and a
hand-rolled cancellation signal over `watch` (this module has no
`tokio-util` dependency, so no off-the-shelf `CancellationToken` --
building the small primitive yourself is the point).

## What's given

- `src/lib.rs` -- a scaffold: the `FetchOutcome` and `FetchReport` types
  (fully defined, not stubs -- these are the shared vocabulary your code
  and the tests both speak), the `Fetcher` trait (a native `async fn` in a
  trait, written in its desugared return-position-`impl Trait` form so it
  can carry an explicit `+ Send` bound), a `TcpFetcher` struct with
  `todo!()` bodies, a hand-rolled `ShutdownSignal`/`ShutdownReceiver` pair
  with `todo!()` bodies, and the `spawn_pipeline` function signature, also
  `todo!()`.
- `src/main.rs` -- an optional, ungraded CLI stub.
- `sandbox18_harness::async_fixture_server` (a dependency, not something
  you write, behind the harness's `async` feature): the `tokio`-based
  counterpart of task 04's fixture server -- same route configuration
  (status/body/delay/`fail_first(n)`) and `stats()` shape, only the I/O is
  async, plus an explicit `shutdown().await` for a deterministic stop.
  `tests/` uses it; you can build your own instance of it too while
  experimenting.
- `tests/` -- the validator. Every test's assertions carry an explanatory
  message.

## What's required

Implement the `todo!()` pieces in `src/lib.rs`:

1. **`TcpFetcher::new`** -- store the four fields.
2. **`impl Fetcher for TcpFetcher`** -- a hand-rolled HTTP/1.1 GET client
   over `tokio::net::TcpStream` (see "The HTTP subset" below), with a
   whole-attempt `tokio::time::timeout` and the retry/backoff contract
   (see below).
3. **`ShutdownSignal::new` / `cancel`, `ShutdownReceiver::is_cancelled` /
   `cancelled`** -- a minimal cancellation signal over
   `tokio::sync::watch`.
4. **`spawn_pipeline`** -- spawn one task per URL into a `JoinSet`, gated
   by a `Semaphore` of `config.concurrency_cap` permits, streaming results
   through a bounded `mpsc` channel of `config.channel_capacity`, honoring
   `shutdown` cooperatively throughout.

### The URL format

Every URL your `TcpFetcher` needs to handle looks like
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

### The retry/backoff contract

`TcpFetcher.max_retries` bounds retries for exactly one failure class:
**connection-level failure** -- either `TcpStream::connect` itself fails,
or the connection is accepted but closes with zero bytes read before a
full status line arrives (this is exactly what the fixture server's
`fail_first(n)` routes do: they accept the TCP connection, then drop it
immediately with no bytes written).

- Each *whole attempt* (connect through reading the full body) is wrapped
  in a single `tokio::time::timeout(request_timeout, ..)`. If that timeout
  fires before the attempt resolves on its own, the outcome is
  `FetchOutcome::Timeout` immediately -- **never retried**, regardless of
  remaining budget. A slow-but-alive server is a different failure mode
  than a dead one, and retrying it just piles up more in-flight requests
  against an already-slow endpoint.
- On a connection-level failure (and only that), sleep for
  `initial_backoff * backoff_multiplier.pow(attempt - 1)` (`attempt` is
  the 1-based number of the attempt that just failed) via
  `tokio::time::sleep`, then retry if budget remains. Total attempt budget
  is `1 + max_retries`.
- If an attempt within that budget succeeds (a full HTTP response is
  read), classify normally (`Healthy`/`Unhealthy`) with `attempts` set to
  however many attempts it actually took.
- If every attempt in the budget fails at the connection level,
  `FetchOutcome::ConnectionFailed { attempts }` with
  `attempts == 1 + max_retries`.
- A non-2xx HTTP response (404, 500, ...) is **not** a connection failure
  and is never retried -- the server answered, it just didn't answer "OK".
  Classify it `Unhealthy` immediately, `attempts: 1`.

### The concurrency cap and backpressure contract

`PipelineConfig.concurrency_cap` is a hard ceiling, enforced by a
`tokio::sync::Semaphore`: at no instant may more than `concurrency_cap`
calls to `Fetcher::fetch` be executing concurrently, regardless of how
many URLs remain queued. This is graded structurally against a fake
`Fetcher`'s own atomic counters -- never against wall-clock elapsed time.

The permit acquired for a URL must stay held for the **whole
fetch-then-send unit**, not just the call to `fetch` -- released only
after the resulting `FetchReport` has been successfully sent (or the task
was cancelled). If you release the permit right after `fetch` returns and
before the send, a slow or non-draining consumer on the other end of the
channel cannot push back on the fetch stage at all, defeating the entire
point of a *bounded* channel.

`PipelineConfig.channel_capacity` is that bound: the `mpsc` channel
`PipelineHandle::receiver` reads from. With `concurrency_cap` permits and
a channel of capacity `channel_capacity`, and nobody draining the
receiver, at most `concurrency_cap + channel_capacity` fetches can ever
be started -- `channel_capacity` reports buffered in the channel, plus up
to `concurrency_cap` tasks blocked mid-send holding their permit. Every
other queued URL cannot even acquire a permit and never calls `fetch` at
all. This is graded structurally too, by counting how many fetches a fake
`Fetcher` actually started.

### The shutdown contract

`ShutdownSignal::cancel` is meant to be called once, from anywhere
(idempotent -- calling it again is a no-op). Every spawned per-URL task
holds a clone of the paired `ShutdownReceiver` and checks it cooperatively
via `select!` at two points: while waiting to acquire a permit, and while
running the fetch-then-send unit once it holds one. Cancelling mid-fetch
means that task's fetch is abandoned, not that the whole pipeline is
torn down forcibly -- no task is ever `abort()`-ed.

`PipelineHandle::join` awaits an internal driver task that itself drains
every spawned per-URL task via a `JoinSet` -- returning from `join` is the
proof that nothing is left running, cancelled or not.
`PipelineOutcome::tasks_spawned` always equals `urls.len()` regardless of
whether shutdown cut the run short (every spawned task is still accounted
for on exit), and `PipelineOutcome::cancelled` reflects whether the
signal had been observed cancelled by the time every task had exited.

## Completion criteria

```bash
cd 18-rust-track
cargo test -p t07-async-fetch-pipeline
```

All given tests pass. They cover, at minimum:

- A fake, in-test `Fetcher` (no sockets) proves url<->outcome pairing (one
  report per URL) and that all four `FetchOutcome` variants survive the
  round trip through the pipeline.
- The concurrency cap, measured structurally by a fake `Fetcher`'s own
  atomic counters (via a `Barrier` forcing deterministic overlap, not
  timing): never exceeded, and genuinely reached given enough URLs.
- Backpressure: with a small `channel_capacity` and a consumer that never
  drains, the fetch stage cannot start more fetches than
  `concurrency_cap + channel_capacity` structurally allows.
- Cooperative shutdown: cancelling the signal makes `PipelineHandle::join`
  return promptly with `cancelled == true` and
  `tasks_spawned == urls.len()`, with nothing left running and no
  `FetchReport` produced by fetches that were still in flight.
- Against the real `TcpFetcher` + `AsyncFixtureServer`: a `200 OK` route
  classifies `Healthy`; `404`/`500` routes classify `Unhealthy` with the
  right status each, `attempts: 1`, never retried; a `fail_first(n)`
  route eventually classifies `Healthy` with `attempts` matching the
  retry/backoff contract when the budget suffices, and
  `ConnectionFailed { attempts }` when it doesn't -- graded by the
  server's own request *count*, never elapsed time; a connection to a
  closed port classifies `ConnectionFailed` after exhausting the retry
  budget; a route delayed past `request_timeout` classifies `Timeout`,
  `attempts: 1`, and is never retried.

## Estimated evenings

2-3

## Topics to read up on

- `async fn` in traits (native, stabilized) vs. the desugared
  return-position-`impl Trait` form, and why an explicit `+ Send` bound
  has to be spelled out on a trait method whose futures will cross a
  `tokio::spawn` boundary
- `tokio::time::timeout` -- what it returns (`Result<T, Elapsed>`), and
  why wrapping a *whole* fallible operation in it is different from
  setting a timeout on the socket directly the way task 04 does
- `tokio::sync::Semaphore` -- `acquire()` vs. `try_acquire()`, and what an
  `OwnedSemaphorePermit` (vs. a permit borrowing the semaphore) buys you
  when a permit needs to move into a spawned task
- `tokio::task::JoinSet` -- spawning a dynamic number of tasks and
  draining them as they finish, vs. holding a `Vec<JoinHandle<_>>` and
  awaiting each one in order
- `tokio::sync::mpsc` (bounded) -- what "bounded" actually changes about
  `Sender::send`'s behavior compared to an unbounded channel, and how
  that becomes real backpressure when a permit is held across the send
- `tokio::sync::watch` -- why `Receiver::changed()` alone can miss a
  change that already happened before you started waiting, and why
  checking the current value first is not optional
- `tokio::select!` -- what "biased" vs. default (random) branch selection
  means, and why racing `shutdown.cancelled()` against real work is the
  whole mechanism cooperative cancellation is built on here
- Connection refused vs. connection reset vs. a genuine timeout -- three
  different failure shapes, easy to conflate if you only match on
  "did the read fail"

## Off-limits

`.authoring/design.md` (at the module root) documents this task's grading
internals -- read it after you're done, if at all, not before.
