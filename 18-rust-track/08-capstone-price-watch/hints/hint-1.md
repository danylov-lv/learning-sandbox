## Parsing shape

A state-machine walk over the input's bytes/chars, tracking a `pos`
cursor, is enough — you don't need a tokenizer/parser split like task 02's
expression language, since this grammar is much smaller:

```
skip whitespace, expect '{'
loop:
    skip whitespace
    if next char is '}': break
    expect '"', read chars until the closing '"' -> this is the field name
    skip whitespace, expect ':'
    skip whitespace
    match field name:
        "product_id" -> expect '"', read chars until closing '"' -> value
        "price" | "scraped_at" -> read a run of [0-9.-] characters -> parse as f64/u64
    skip whitespace
    if next char is ',': consume it, continue loop
    else: expect '}', break
after the loop: make sure all three fields were actually seen, else MissingField
```

`str::char_indices()` gives you both the byte position (for `ParseError`'s
`pos` field) and the `char` in one pass. `f64::from_str` / `u64::from_str`
on the sliced numeric run does the actual number parsing — you don't need
to hand-roll digit accumulation yourself, just find where the run of
valid number characters starts and ends.

## `fetch_price`'s async I/O shape

This is task 04's `HttpChecker` translated to `tokio`, nothing more:

```rust
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::net::TcpStream;

// base_url looks like "http://127.0.0.1:53214" -- strip the scheme, split on ':'
let addr = base_url.trim_start_matches("http://");
let mut stream = TcpStream::connect(addr).await.map_err(IngestError::Connect)?;

let request = format!("GET {path} HTTP/1.1\r\nHost: {addr}\r\nConnection: close\r\n\r\n");
stream.write_all(request.as_bytes()).await.map_err(IngestError::Io)?;

let mut reader = BufReader::new(stream);
let mut status_line = String::new();
reader.read_line(&mut status_line).await.map_err(IngestError::Io)?;
// parse the numeric status out of "HTTP/1.1 200 OK"

let mut content_length = 0usize;
loop {
    let mut line = String::new();
    reader.read_line(&mut line).await.map_err(IngestError::Io)?;
    let trimmed = line.trim();
    if trimmed.is_empty() { break; }               // blank line ends the header block
    if let Some((k, v)) = trimmed.split_once(':') {
        if k.trim().eq_ignore_ascii_case("content-length") {
            content_length = v.trim().parse().unwrap_or(0);
        }
    }
}

let mut body = vec![0u8; content_length];
reader.read_exact(&mut body).await.map_err(IngestError::Io)?;
let body = String::from_utf8_lossy(&body);
```

then check the status (non-2xx -> `IngestError::Status`) before parsing
the body, since a non-2xx response's body was never a price payload to
begin with.

## `ingest_batch`'s concurrency shape

```rust
use std::sync::Arc;
use tokio::sync::Semaphore;
use tokio::task::JoinSet;

let semaphore = Arc::new(Semaphore::new(concurrency_cap));
let mut set = JoinSet::new();
for path in paths {
    let permit_source = Arc::clone(&semaphore);
    let base_url = base_url.to_string();
    let path = path.clone();
    set.spawn(async move {
        let _permit = permit_source.acquire_owned().await.expect("semaphore never closes");
        let result = fetch_price(&base_url, &path).await;
        FetchAttempt { path, result }
        // _permit drops here, at the end of this task -- not before the fetch
        // finishes, which is the whole point: it's held for the request's
        // entire lifetime, not just while acquiring it.
    });
}

let mut attempts = Vec::new();
while let Some(joined) = set.join_next().await {
    attempts.push(joined.expect("ingest task panicked"));
}
```

`join_next()` returns tasks in **completion order**, which is exactly why
`IngestReport::attempts` is documented as not matching `paths`' order —
don't sort it back into input order, that would hide the very
concurrency this function is required to have. Once every attempt is
collected, loop over the successful ones and call `put_latest_price`
sequentially, back in this function — `Store` never needs to be `Send`
this way, since it's never touched from inside a spawned task.
