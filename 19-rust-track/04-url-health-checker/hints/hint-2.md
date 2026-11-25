## Reading the response

Wrap the connected `TcpStream` in a `std::io::BufReader` -- it gives you
`read_line` for the status line and each header line (a blank line, just
`"\r\n"`, ends the header block), and you can keep reading from the same
`BufReader` afterward for the body without losing any bytes it
buffered ahead. Parse the status code out of the status line by splitting
on whitespace (`HTTP/1.1 200 OK` -- the second token). For headers, split
each line once on `:` and compare the key case-insensitively
(`eq_ignore_ascii_case`) against `"content-length"`. Once you have that
number, `Read::read_exact` into a buffer of exactly that many bytes reads
the body without over- or under-reading.

Set both timeouts on the stream before you do any reading:
`TcpStream::connect_timeout(&addr, duration)` for the connect itself
(plain `connect` has no timeout), and `set_read_timeout(Some(duration))`
right after a successful connect, before your first `read_line`. A read
that exceeds the timeout comes back as an `Err` -- check its `.kind()`
(`ErrorKind::WouldBlock` or `ErrorKind::TimedOut`, platform-dependent) to
recognize "this was a timeout" specifically, rather than treating every
`io::Error` the same way.

A connection-level failure looks different from a timeout in your code:
`connect_timeout` returning `Err` directly is one case; a successful
connect followed by `read_line` returning `Ok(0)` (zero bytes, meaning a
clean EOF before you got anything) is the other -- that's what a
`fail_first(n)` route's dropped connection looks like from the client
side. Both belong in the "retry this" bucket; a timed-out read does not.

## The pool

Put the URLs behind something several threads can pull from without
tearing each other's hands off: a `Mutex<VecDeque<String>>` (each worker
locks it, pops the front, unlocks, works) is the most literal shared
queue. An `Arc<AtomicUsize>` incrementing an index into a shared `&[String]`
slice is a lock-free alternative that does the same job for this
particular case (no removals needed, just "give me the next one"). Either
is fine -- the trait bound and pool signature don't care which you pick.

`std::thread::scope` lets your worker closures borrow `checker` and the
queue by reference instead of needing `Arc` everywhere, since the scope
guarantees every spawned thread finishes before the scope block returns.
Give each worker thread its own clone of an `mpsc::Sender<HealthReport>`;
have the scope's outer code hold the one `Receiver` and collect from it
after spawning (or while the scope runs, then join). The receiver knows
there are no more messages once every sender clone has been dropped --
that happens automatically when each worker thread ends, as long as you
don't keep an extra clone alive outside the worker closures.
