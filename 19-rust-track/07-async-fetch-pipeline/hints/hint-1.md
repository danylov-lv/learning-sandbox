This task is three separate, smaller problems stacked on top of each other:
"read one HTTP response off an async socket," "retry that with backoff on
the right failure class," and "run many of those under a hard concurrency
cap, streamed through a bounded channel, cancellable at any point." Solve
them in that order. Get a single URL fetching correctly with no retry logic
at all before you touch `spawn_pipeline`, and get `spawn_pipeline` working
with an always-succeeding fake `Fetcher` before you plug in the real
`TcpFetcher`.

The HTTP-reading half is the same shape as task 04's, just over
`tokio::net::TcpStream` instead of `std::net::TcpStream`, and with
`tokio::io::AsyncBufReadExt`/`AsyncReadExt`/`AsyncWriteExt` standing in for
the synchronous `Read`/`Write`/`BufRead` traits you'd use there. If you've
already done 04, most of that parsing logic ports over almost unchanged
with `.await` added at each I/O call.

The new part in this task is wrapping a *whole attempt* -- connect, write,
read status line, read headers, read body -- in a single
`tokio::time::timeout`, rather than setting separate timeouts on the socket
the way 04 does. That single wrapping is also what makes a `Timeout`
outcome and a `ConnectionFailed` outcome distinguishable: one comes from the
timeout firing, the other from the inner future itself resolving to an
error before the timeout does.

For the concurrency half, don't reach for `tokio-util`'s `CancellationToken`
or an off-the-shelf worker-pool crate -- there isn't one on this module's
dependency list, on purpose. `tokio::sync::Semaphore` (the cap),
`tokio::task::JoinSet` (spawn-and-track-many), `tokio::sync::mpsc` (the
bounded output channel), and `tokio::sync::watch` (the shutdown signal) are
the whole toolbox, and each one is small enough to read the docs for in a
few minutes.
