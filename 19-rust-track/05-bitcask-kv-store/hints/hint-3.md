## `compact`, concretely

```
new_path = dir.join("data.bitcask.compacting")
new_file = create/truncate new_path, wrap in BufWriter

new_keydir = empty HashMap

for (key, location) in self.keydir.iter():           // only live keys — dead ones
                                                      // were never in the keydir at all
    value = read location.value_len bytes at location.value_offset from the OLD file
    offset_of_new_record = new_file's current position
    write the framed record (checksum, key_len, value_len, key, value) to new_file
    new_keydir.insert(key.clone(), RecordLocation {
        value_offset: offset_of_new_record + 12 + key.len(),
        value_len: location.value_len,
        file_id: <same constant you always use>,
    })

new_file.flush()
new_file.sync_all()
drop(new_file)                 // <-- see the Windows note below, this line matters
drop(self.write_handle)        // and this one
drop(self.read_handle)         // and this one, if you kept a long-lived read handle

fs::rename(new_path, old_path)  // atomically replaces old_path with new_path's contents

self.keydir = new_keydir
self.write_handle = reopen old_path for appending, positioned at end
self.read_handle = reopen old_path for reads
```

## Windows: why the `drop`s above are not optional

`std::fs::rename` on Windows fails with a sharing-violation error if
*this same process* still has an open handle to the destination path
(`old_path`, i.e. `data.bitcask`) — this includes your `Store`'s own
append handle and any read handle you're holding onto. On Linux/macOS,
renaming over a file with open handles just works (the open handles keep
referring to the old inode, now unlinked, until they're closed) — which
means if you only ever run your own ad-hoc tests on Linux, this bug is
invisible there and only shows up here, on Windows, in the given tests.

The fix is exactly the ordering above: finish writing and syncing the
*new* file, then explicitly close (drop) every handle your `Store` holds
open on the *old* file, **then** rename, **then** open fresh handles on
the renamed-into-place file. If your `Store`'s fields hold `File` or
`BufWriter<File>` directly, setting them to something else (or wrapping
in `Option` and taking it before the rename) forces the drop at the right
moment; don't rely on them happening to go out of scope in the right
order on their own.

## Why the exact-size assertion in the compaction test is fair game

The compaction test checks the post-compaction file size *exactly*
(`12 + key_len + value_len`, summed over the surviving keys), not just
"smaller than before." That's only possible to assert exactly because
the record format itself is fully pinned in the README — there's no
implementation-defined padding, alignment, or per-file header to account
for. If your `compact` writes anything else (a file-level header, a
count-of-records prefix, trailing padding for alignment) that isn't part
of the per-record format in the README, this test will catch it — which
is the point: the format is the *whole* file, not "the format, plus
whatever else seemed convenient."
