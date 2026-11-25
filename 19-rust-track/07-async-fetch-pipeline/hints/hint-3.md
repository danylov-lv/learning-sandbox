Prose sketches close to pseudocode. You still have to write and debug the
actual Rust -- nothing here is copy-pasteable.

## `TcpFetcher::new`

Just `Self { request_timeout, max_retries, initial_backoff, backoff_multiplier }`.
No logic.

## `impl Fetcher for TcpFetcher`

```
fn fetch(url) -> impl Future<Output = FetchOutcome> + Send {
    // copy everything out of &self / url first, the returned future must
    // not borrow past this call
    async move {
        let (host, port, path) = parse_url(&url);
        let mut attempts = 0;
        loop {
            attempts += 1;
            match tokio::time::timeout(request_timeout, one_attempt(&host, port, &path)).await {
                Ok(AttemptResult::Response(status)) => return classify(status, attempts),
                Ok(AttemptResult::ConnectionFailed) if attempts <= max_retries => {
                    let backoff = initial_backoff * backoff_multiplier.pow(attempts - 1);
                    tokio::time::sleep(backoff).await;
                    continue;
                }
                Ok(AttemptResult::ConnectionFailed) => return FetchOutcome::ConnectionFailed { attempts },
                Err(_elapsed) => return FetchOutcome::Timeout,
            }
        }
    }
}
```

Where `classify(status, attempts)` is `if (200..300).contains(&status) { Healthy } else { Unhealthy }`,
both carrying `attempts`. `one_attempt` is the part that actually touches
the socket -- `TcpStream::connect` (map any `Err` to `ConnectionFailed`),
write the request line + `Host` header + `Connection: close` + blank line,
then `read_line`/`read_exact` as described in hint-2, mapping `Ok(0)` and
any I/O `Err` to `ConnectionFailed` too. Note that `one_attempt` itself
never needs to know about timeouts at all -- `tokio::time::timeout` around
the whole call is what turns "this took too long" into `Err(Elapsed)`
without `one_attempt` doing anything special.

## `ShutdownSignal` / `ShutdownReceiver`

```
ShutdownSignal::new() -> (Signal, Receiver) {
    let (tx, rx) = tokio::sync::watch::channel(false);
    (Signal { tx }, Receiver { rx })
}
cancel(&self) { let _ = self.tx.send(true); }
is_cancelled(&self) -> bool { *self.rx.borrow() }
async fn cancelled(&mut self) {
    loop {
        if self.is_cancelled() { return; }
        if self.rx.changed().await.is_err() { return; } // sender dropped
    }
}
```

## `spawn_pipeline`

```
fn spawn_pipeline(fetcher, urls, config, shutdown) -> PipelineHandle {
    let (tx, rx) = tokio::sync::mpsc::channel(config.channel_capacity);
    let semaphore = Arc::new(Semaphore::new(config.concurrency_cap));
    let tasks_spawned = urls.len();

    let mut join_set = JoinSet::new();
    for url in urls {
        let (fetcher, semaphore, tx) = (fetcher.clone(), semaphore.clone(), tx.clone());
        let mut shutdown = shutdown.clone();
        join_set.spawn(async move {
            let permit = tokio::select! {
                _ = shutdown.cancelled() => return,
                permit = semaphore.acquire() => permit,
            };
            let _permit = permit.expect("semaphore never closes");
            tokio::select! {
                _ = shutdown.cancelled() => {}
                outcome = fetcher.fetch(&url) => {
                    let _ = tx.send(FetchReport { url, outcome }).await;
                }
            }
            // _permit drops here either way, releasing it back to the semaphore
        });
    }
    drop(tx); // the original sender: lets rx observe "done" once every per-url clone drops too

    let mut shutdown = shutdown;
    let driver = tokio::spawn(async move {
        while join_set.join_next().await.is_some() {}
        PipelineOutcome { tasks_spawned, cancelled: shutdown.is_cancelled() }
    });

    PipelineHandle { receiver: rx, driver }
}
```

Three details worth double-checking once this compiles:

- The **second** `select!` covers `fetcher.fetch(&url).await` *and*
  `tx.send(..).await` as one unit (wrap them together, e.g. inside the same
  `async` block passed to `select!`, or await the fetch first and then
  race `shutdown.cancelled()` against the send too) -- if you only guard
  the fetch and let the send run unconditionally afterward, a cancelled
  pipeline can still block forever trying to push into a full channel
  nobody is draining.
- The permit (`_permit`) must stay alive across that entire second
  `select!`, not just during the call to `fetch`. Binding it to a name
  that lives until the end of the spawned task's async block (rather than,
  say, dropping it right after `fetch` returns and before the send) is
  what makes the bounded channel's backpressure actually reach back to the
  concurrency cap.
- `PipelineOutcome::cancelled` is read from the shutdown receiver *after*
  every task has already exited (inside the driver, after the `join_set`
  drain loop) -- so it reflects the final state, not whatever it happened
  to be at spawn time.
