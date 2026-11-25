## `Store`'s fields

```rust
use std::collections::HashMap;
use std::fs::File;
use std::io::BufWriter;

struct RecordLocation {
    value_offset: u64,
    value_len: u32,
}

pub struct Store {
    dir: std::path::PathBuf,
    writer: BufWriter<File>,   // positioned at end-of-file, append-only
    keydir: HashMap<Vec<u8>, RecordLocation>,
}
```

You'll also want a way to read (seek + read_exact) for `get` — either a
second, independent `File` handle opened read-only, or a fresh `File::open`
per call. Two handles onto the same path, one appending and one reading,
is completely fine on both Windows and Unix as long as neither is being
renamed or deleted while the other is open (this task never renames or
deletes the data file at all — that's a task-05-only concern, from
compaction, which this task doesn't have).

## Replay loop on `open`

Same shape as task 05's, minus the tombstone branch:

```
loop over the file from offset 0:
    read 12 bytes for the header
        -> 0 bytes read: clean EOF, stop, no error
        -> 1..12 bytes read: torn header, stop, no error
    parse checksum, key_len, value_len from the header
    read key_len bytes for the key
        -> short read: torn record, stop, no error
    read value_len bytes for the value
        -> short read: torn record, stop, no error
    recompute checksum over (key_len_le, value_len_le, key, value)
        -> mismatch: torn/corrupt record, stop, no error
    keydir.insert(key, RecordLocation { value_offset: record_start + 12 + key_len, value_len })
    advance offset past this record
```

`Read::read_exact` is the mechanism for "torn read detection": it returns
`Err(ErrorKind::UnexpectedEof)` the instant there aren't enough bytes left
to fill the buffer — exactly the signal for "this header/key/value is
truncated, stop replay here." Track the offset where the loop stops; that's
both where your writer should start appending from and the length you
`File::set_len` the file down to before returning from `open`.

## Why `put`'s own `flush()` (not `sync_all`) matters

If `get` opens its own independent read handle, that handle only sees
bytes the OS actually has. A `BufWriter` that hasn't had its own buffer
pushed out (`BufWriter::flush()`, cheap, no syscall to the disk itself —
just "hand these bytes to the OS") hasn't given the OS those bytes at
all, so a second handle genuinely can't see them yet. Call the writer's
plain `.flush()` after every `put` unconditionally; reserve
`File::sync_all` (expensive, actually durable) for the public `Store::flush`
method only. This is the same split task 05's README describes in more
depth if you want the full reasoning.

## Computing exact byte offsets in tests (for your own debugging)

A record is `12 + key_len + value_len` bytes; in this task `value_len` is
always 16 (`encode_price_value` always produces exactly 16 bytes), so a
record for product id of length `n` is always `28 + n` bytes. If you want
to sanity-check the crash-recovery test's byte-offset math by hand, that's
the formula it uses.
