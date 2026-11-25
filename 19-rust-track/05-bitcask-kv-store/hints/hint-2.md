## Framing

`u32::to_le_bytes()` gives you `[u8; 4]`; write those four bytes with
`Write::write_all`. Reading back: `Read::read_exact` into a `[0u8; 4]`
buffer, then `u32::from_le_bytes(buf)`. `read_exact` is the mechanism you
want for "torn read detection" too — it returns an `Err` (specifically
`ErrorKind::UnexpectedEof`) the moment there aren't enough bytes left to
fill the buffer, which is exactly the signal that tells you "this header
(or key, or value) is truncated, stop replay here."

## The keydir's shape

Something like:

```rust
struct RecordLocation {
    file_id: u64,
    value_offset: u64,
    value_len: u32,
}

// inside Store:
keydir: HashMap<Vec<u8>, RecordLocation>,
```

`get` becomes: look up the key, `Seek::seek(SeekFrom::Start(value_offset))`
on a read handle, `read_exact` for `value_len` bytes. No need to
re-read or re-check the key on a `get` — you already trust the keydir,
which was itself built from validated records during replay.

## Replay loop shape

```
loop over the file from offset 0:
    read 12 bytes for the header
        -> 0 bytes read: clean EOF, stop, no error
        -> 1..12 bytes read: torn header, stop, no error
    parse checksum, key_len, value_len_field from the header
    read key_len bytes for the key
        -> short read: torn record, stop, no error
    if value_len_field != TOMBSTONE:
        read value_len_field bytes for the value
            -> short read: torn record, stop, no error
    recompute checksum over (key_len_le, value_len_field_le, key, value)
        -> mismatch: torn/corrupt record, stop, no error
    apply to keydir (insert or remove), advance offset past this record
```

Track the byte offset where this loop stops — that's both the position
your writer should start appending from, and the length you truncate the
file down to (`File::set_len`) before returning from `open`.

## Two separate file handles, or one?

You need to both *seek and read* (for `get`, and for replay on open) and
*append* (for `put`/`delete`). A single `File` handle can do both if you
seek to the end before every write — but that's an extra syscall per
write and easy to get subtly wrong under buffering. Consider keeping a
`BufWriter<File>` positioned at the end for appends, and a *separate*
`File` (or `BufReader<File>`, reseeked per call) for reads — two
independent handles onto the same path is completely fine on both Unix
and Windows, since neither of them is being renamed or deleted while
they're both open. (The place a second handle *does* matter is
`compact` — see hint-3.)

If you go this route (a `BufWriter` for appends, a separate handle for
reads), make sure `put`/`delete` call the writer's own `flush()` — not
`sync_all`, just `flush()` — before returning. Otherwise a `get` that
opens its own fresh handle right after a `put` can find nothing there:
the bytes are still sitting in the `BufWriter`'s in-process buffer,
which a second, independent handle on the same file has no way to see.
This has nothing to do with the crash-durability contract (that's what
`sync_all`, gated behind the public `flush()` method, is for) — it's
just about getting bytes out of your own buffer and into the OS at all.
