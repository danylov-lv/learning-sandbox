## Reading the response, async-style

Wrap the connected `TcpStream` in a `tokio::io::BufReader` -- it gives you
`AsyncBufReadExt::read_line` for the status line and each header line (a
blank line, just `"\r\n"`, ends the header block), and you can keep reading
from the same `BufReader` afterward for the body without losing any bytes
it buffered ahead. Parse the status code out of the status line by
splitting on whitespace (`HTTP/1.1 200 OK` -- the second token). For
headers, split each line once on `:` and compare the key
case-insensitively (`eq_ignore_ascii_case`) against `"content-length"`.
Once you have that number, `AsyncReadExt::read_exact` into a buffer of
exactly that many bytes reads the body without over- or under-reading.

`read_line` returning `Ok(0)` is a clean EOF before you got anything --
exactly what a `fail_first(n)` route's dropped connection looks like from
the client side, and exactly what `TcpStream::connect` itself failing
outright looks like too. Both are connection-level failures. Neither of
those is what `tokio::time::timeout` is for -- the timeout wraps the
*entire* attempt (connect through body), so a genuinely slow-but-alive
server surfaces as the timeout future winning the race, while a
dead/refused/dropped connection surfaces as the inner future resolving to
an error or an EOF well before the timeout would have fired anyway.

## The retry/backoff contract

Exactly one failure class retries: connection-level failure (connect
error, or EOF before a full status line arrives). A non-2xx HTTP response
is a real answer and is never retried. A timeout is never retried either
-- it gets its own outcome variant with no `attempts` field for exactly
this reason.

The attempt budget is `1 + max_retries` total attempts. Track an `attempts`
counter starting at 0, incrementing at the top of each loop iteration
before you try anything. Between a failed attempt and the next one (only
when budget remains), sleep for
`initial_backoff * backoff_multiplier.pow(attempts - 1)` via
`tokio::time::sleep` -- `attempts` here is the attempt number that just
failed, so the very first retry sleeps for exactly `initial_backoff`
(multiplier to the power of zero), and each subsequent retry's sleep grows
by a factor of `backoff_multiplier`.

## The shutdown primitive

`tokio::sync::watch::channel(false)` gives you a `Sender<bool>` and a
`Receiver<bool>` that both start at `false`. `ShutdownSignal::cancel`
just sends `true`. The subtlety is entirely in `ShutdownReceiver::cancelled`:
a bare `self.rx.changed().await` is not enough on its own, because
`changed()` only resolves on the *next* change after this call started
waiting -- if `cancel()` already happened before you called `cancelled()`,
there may be no future change coming, and you'd hang forever. Check the
current value first (`*self.rx.borrow()`), and only fall through to
awaiting `changed()` if it's still `false` -- in a loop, since `changed()`
can also spuriously wake for reasons unrelated to your specific interest.
