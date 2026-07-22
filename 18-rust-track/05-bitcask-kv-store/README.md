# 05 — Bitcask KV Store

## Backstory

The scraper (module 13's world, in spirit) needs somewhere to remember
which pages it has already visited and what it scraped from each one —
dedup keys, last-seen timestamps, small cached fragments — across process
restarts. There's no database server to point it at: this runs on a
worker box with local disk and nothing else, and standing up Postgres or
Redis for a few hundred thousand small key-value pairs is a lot of
infrastructure for "remember this between crashes." What it actually needs
is exactly what Bitcask (the storage engine behind Riak) was built for: an
embedded, crash-safe key-value store that is *just a file*, with no server
process, no schema, and a recovery story that survives the worker getting
`kill -9`'d mid-write, because on a long-running scrape, eventually it
will be.

This task builds that engine: an append-only log of records, an
in-memory index over it, replay-based recovery, and compaction to reclaim
space that overwrites and deletes leave behind.

## What's given

- `src/lib.rs` — the scaffold. A `Store` type (currently a unit struct —
  shape it however you need), a two-variant `Error` enum with `Display`,
  `std::error::Error`, and `From<io::Error>` already wired (ordinary
  plumbing, not the lesson), and every `Store` method as a documented
  signature ending in `todo!()`. The doc comments on each method restate
  the relevant piece of this README's contract, but this README is the
  actual spec — if the two ever seem to disagree, this file wins.
- `Cargo.toml` — already has `tempfile` and `sandbox18-harness` wired as
  dev-dependencies for the tests.
- `tests/` — the GIVEN validator. Do not weaken or remove assertions here;
  see "Completion criteria."

## What's required

Implement every method on `Store` so that it satisfies the on-disk format,
durability contract, and compaction contract below, precisely — this
format is specified exactly enough that there is exactly one correct
on-disk byte layout, not "a reasonable one."

### On-disk format

A store is a directory. Inside it, exactly one file matters:
`DATA_FILE_NAME` (`"data.bitcask"`, exported as a constant from this
crate so tests — and you, while debugging — can find it without
duplicating the name).

That file is an append-only sequence of **records**. Every record has
this exact byte layout, all multi-byte integers little-endian
(`to_le_bytes` / `from_le_bytes`):

```
byte offset   field          size      meaning
-----------   -----          ----      -------
0             checksum       4 bytes   u32, see "Checksum" below
4             key_len        4 bytes   u32, length of key in bytes
8             value_len      4 bytes   u32, length of value in bytes,
                                        OR the sentinel TOMBSTONE
                                        (0xFFFF_FFFF) meaning "this
                                        record deletes its key"
12            key bytes      key_len   raw key bytes
12+key_len    value bytes    value_len raw value bytes — ABSENT
                                        entirely (zero bytes on disk)
                                        when value_len is TOMBSTONE
```

So a live record is `12 + key_len + value_len` bytes on disk; a tombstone
record is `12 + key_len` bytes (no value payload at all — not even a
zero-length one written as a marker, the sentinel *is* the marker).

A real value can be any length up to `u32::MAX - 1`; `u32::MAX` itself is
reserved and can never be a real value's length. This is a deliberate
simplification (not "0xFFFF_FFFF minus a flag bit somewhere") — it costs
4 GiB of unreachable value length in exchange for a format with no
separate flag byte to keep in sync with the length fields.

#### Checksum

The checksum is **FNV-1a, 32-bit**, computed over every byte of the
record *except* the checksum field itself — i.e. over
`key_len_le ++ value_len_field_le ++ key_bytes ++ value_bytes` (value
bytes omitted for a tombstone, exactly as they're omitted on disk):

```
fn fnv1a32(data: &[u8]) -> u32 {
    let mut hash: u32 = 0x811c_9dc5;      // FNV offset basis
    for &b in data {
        hash ^= b as u32;
        hash = hash.wrapping_mul(0x0100_0193); // FNV prime
    }
    hash
}
```

This is pinned exactly (not "a checksum of your choice") because it's
part of what makes a record's bytes verifiable at all — a record whose
checksum doesn't match its own length-and-payload bytes is exactly what
"corrupt" means for this format. Note it covers the length fields too,
not just the payload: a torn write that corrupts `key_len` or `value_len`
(rather than the payload bytes) must still be caught, or replay would try
to read a nonsense number of bytes for the key or value.

#### Keydir

The in-memory index — call it whatever you like internally — maps each
live key to where its current value lives:

```
key: Vec<u8>  ->  (file_id, value_offset, value_len)
```

`value_offset` is the byte offset of the *value bytes themselves* (i.e.
`record_start + 12 + key_len`), not the record start — so a `get` can
seek straight to the value without re-reading or re-checking the key.
`file_id` exists in the keydir for conceptual fidelity with real Bitcask,
which keeps many immutable segment files plus one active file; this task
deliberately narrows that to a single always-current data file (compact
below explains why), so in this implementation `file_id` is always the
same constant — but the field stays in the tuple/struct so the shape
matches what a multi-segment version would look like, and so `compact`
has an obvious place to put a real answer if you ever extend this past
the task.

A tombstone record is never present in the keydir — writing one removes
the key from the keydir (if it was there), full stop.

### Recovery (log replay on open)

`Store::open` reads `DATA_FILE_NAME` from the start, one record at a
time, rebuilding the keydir as it goes:

1. Read 12 bytes for the header. Exactly 0 bytes read at a record
   boundary means a clean end of file — replay is done, no error.
2. Any other short read (1–11 bytes) means a **torn header** — stop
   replay here, treating the file as if it ended at the start of this
   record. Not an error.
3. Read `key_len` bytes for the key (and, unless `value_len` is
   `TOMBSTONE`, `value_len` bytes for the value). A short read at either
   step is a **torn record** — same handling: stop replay at the start
   of this record, not an error.
4. If both reads succeed, recompute the checksum over the bytes just
   read and compare to the stored one. A mismatch is treated exactly like
   a torn record: stop replay at the start of this record. (In practice
   this task's tests only produce corruption via truncation, which is
   caught by steps 2–3 already — but a real crash can in principle leave
   a full-length record with garbage bytes instead of a short one, and
   the checksum is what catches that case, so don't skip checking it.)
5. On a valid record: apply it to the keydir (insert/update for a live
   record, remove for a tombstone) and advance to the next record.

**The rule in one sentence: replay stops at the first record that
doesn't fully and correctly parse, and everything before that point is
kept — never fewer records than were validly written, never a
corrupted/partial record accepted as valid.** `Store::open` returns
`Err` only for an actual I/O failure (e.g. the directory doesn't exist),
never merely because the file's tail is torn.

After replay stops (whether at a clean EOF or a torn/corrupt record),
**truncate the data file down to exactly the offset where replay
stopped**, before returning from `open`. If you skip this and simply
start appending from the old (pre-truncation) end of the file, a torn
tail from a previous crash sits as garbage between the last good record
and your new writes, and the *next* recovery pass would stop at that old
garbage instead of reading past it to the new records behind it. `open`
must leave the file in a state where "the file's length" and "the offset
right after the last valid record" are the same number.

### Durability

Writes go through a buffered writer. **A write is not guaranteed to
survive a crash until `flush` is called.** Concretely:

- Before `flush`, a `put` or `delete` may be sitting in an in-memory
  buffer, an OS page cache, or both — a crash can lose it entirely, and
  that's fine and expected.
- After `flush` returns `Ok`, every record appended before that call is
  guaranteed present and intact if the store is reopened after a crash.
  `flush` must therefore do two things: flush the buffered writer (get
  the bytes to the OS) *and* sync the underlying file (get the OS to put
  them on durable storage — `File::sync_data` or `sync_all`). Either one
  alone is not the guarantee this contract asks for.
- `Drop` calls `flush` as a convenience (so an orderly `Store` going out
  of scope doesn't lose its last writes for no reason), but a `Drop` body
  can't surface an error, so it is not a substitute for calling `flush`
  yourself anywhere the guarantee actually matters.

**This is a durability guarantee, not a visibility one — don't conflate
the two.** `get` must always return the most recently `put` value for a
key in the same process, even if `flush` was never called. That's
ordinary read-your-own-writes correctness, not the crash guarantee above:
a `put` followed immediately by a `get` (no `flush` in between) is the
very first thing `tests/basic.rs` checks, and it must pass. The subtlety
is that if `get` opens its own independent file handle to read the value
back (a reasonable design — see hint-2), that handle only sees bytes the
OS actually has, and a `BufWriter` that hasn't had its *own* buffer
pushed out yet (a plain `BufWriter::flush()`, not `sync_all`) hasn't
given the OS those bytes at all — a second handle on the same file
genuinely cannot see them yet, no reordering or caching trick fixes that
from the read side. If your very first put-then-get test fails with an
unexpected-EOF-shaped error even though the write logic looks right, this
is almost certainly why. The fix costs nothing durability-wise: call the
writer's own `flush()` after every `put`/`delete` unconditionally (cheap —
it's just handing bytes to the OS, not syncing them to disk), and reserve
the expensive `sync_all` exclusively for the public `Store::flush`
method. That split — always flush the buffer, only sometimes fsync — is
the whole trick.

The crash-recovery test does not wait for a real crash — it calls
`flush` to make some records durable, then **truncates the data file
directly, through a raw file handle, not through `Store`**, chopping off
part of a subsequent record's bytes. That's this test suite's stand-in
for "the OS had only written part of the last `write()` call when the
process died." Recovery (the "Recovery" section above) must handle it
without erroring and without losing anything from before the cut.

### Compaction

Over time, overwrites and deletes leave dead bytes behind: an
overwritten key's old value is still sitting in the file (the keydir
just doesn't point at it anymore), and a deleted key's tombstone is
itself a permanent record until compaction removes it. `compact`:

1. Walks the current keydir (i.e. only *live* keys — dead values and
   tombstones are never carried forward).
2. Writes each live key's current value as a fresh record into a new
   file, in this format, in whatever order you like.
3. Flushes and syncs the new file.
4. Atomically replaces the old data file with the new one (e.g. write to
   `data.bitcask.compacting` in the same directory, then rename it over
   `data.bitcask`), and repoints the keydir at the new file's offsets.

After `compact` returns `Ok`: every key that was live before the call
reads back the identical value it did before (correctness), **and** the
data file's size is now exactly the sum of `12 + key_len + value_len`
over just the surviving live records — not "smaller," exactly that,
since the format is fully pinned and a compacted file has no reason to
contain anything else. (A test that only checked "smaller" would pass a
buggy compaction that deletes half the live keys along with the dead
space; a test that only checked "every live key still reads back
correctly" would pass a `compact` that does nothing at all. The given
tests check both — plus the exact resulting size, since that's legitimate
here: it's arithmetic over a format this README fully specifies, not a
guess about implementation overhead.)

**Windows note (read this before implementing `compact`):** unlike
POSIX, Windows will not let you delete or rename a file while any handle
to it — in this process — is still open, and this bites here in exactly
one place: if `Store` is holding an open `File`/`BufWriter` on the
*old* `data.bitcask` for appending, you must close/drop that handle
before renaming the new file over it, or the rename fails with a sharing
violation. (This is also true of any lingering read handle you may have
opened for the rewrite itself — close it once you're done reading, don't
hold it past the rename.) On POSIX this same code would silently work
even without dropping the handle first, since POSIX allows renaming over
a file that's still open elsewhere — so if you only test this on Linux,
this bug won't show up until it runs here. Drop the old writer, then
rename, then reopen a fresh writer on the (renamed-into-place) file.

### Public API this task grades

```rust
pub const DATA_FILE_NAME: &str;
pub const TOMBSTONE: u32;              // = u32::MAX

pub enum Error { Io(io::Error), Corrupt(String) }
pub type Result<T> = std::result::Result<T, Error>;

impl Store {
    pub fn open(dir: impl AsRef<Path>) -> Result<Self>;
    pub fn get(&self, key: &[u8]) -> Result<Option<Vec<u8>>>;
    pub fn put(&mut self, key: Vec<u8>, value: Vec<u8>) -> Result<()>;
    pub fn delete(&mut self, key: &[u8]) -> Result<()>;
    pub fn flush(&mut self) -> Result<()>;
    pub fn keys(&self) -> Vec<Vec<u8>>;
    pub fn len(&self) -> usize;
    pub fn is_empty(&self) -> bool;
    pub fn compact(&mut self) -> Result<()>;
}
// Drop flushes best-effort.
```

#### Why `get` borrows and `put` owns (a design question, not an accident)

`get(&self, key: &[u8])` takes a *borrowed* key: looking something up is
read-only and momentary, so there is no reason to force a caller who
already owns a `Vec<u8>` (or who has one borrowed from somewhere else
entirely, e.g. a slice of a larger buffer) to hand over ownership just to
ask "do you have this?" It returns an *owned* `Vec<u8>`, not a borrowed
slice, for a reason that has nothing to do with API taste and everything
to do with where the data actually lives: the value isn't sitting in
memory inside `Store` waiting to be borrowed from — it's on disk, and
`get` has to go read it. There is no `&self`-lifetime buffer to hand a
reference into (and even if there were an internal read-cache, handing
back `&[u8]` tied to `&self` would forbid a second `get` call — or a
`put` — while the first result is still alive, which would make the API
nearly unusable).

`put(&mut self, key: Vec<u8>, value: Vec<u8>)` takes *owned* data for
both, and deliberately not `&[u8]`: the keydir has to hold onto the key
indefinitely — as long as the key is live, full stop, not just for the
duration of this call — so `Store` is going to end up owning a copy of
those bytes no matter what the signature says. Accepting `&[u8]` and
cloning internally would hide that allocation behind a signature that
looks like it might not need one; accepting owned `Vec<u8>` says
honestly "yes, this call needs an allocation you already have to
provide, and here it is." Whether `value` similarly needs to be retained
in memory (vs. written straight to disk and forgotten) is a design choice
this format leaves to the log itself — but taking it as owned still
avoids a needless clone at the call site when the caller already had
ownership to give.

`delete(&mut self, key: &[u8])`, by contrast, takes a *borrowed* key: it
doesn't need to retain `key` past the call — whatever it needs on disk
(the tombstone record's own copy of the key bytes) it writes out of the
borrow directly, and whatever it removes from the keydir it removes by
comparing against the borrow, never by keeping it around afterward.

## Completion criteria

```bash
cargo test -p t05-bitcask-kv-store
```

is the validator. All of `tests/` must pass. Every assertion in the
given tests carries a message explaining what it means if it fails — read
those messages, they're the diagnosis. In particular:

- `tests/basic.rs` — put/get/overwrite/delete semantics, `keys()` listing
  only live keys, and one assertion of the exact on-disk record size for
  a single put, derived directly from the format above (`12 + key_len +
  value_len`) — a sanity check that your framing matches the spec byte
  for byte, not just "close enough."
- `tests/reopen.rs` — close the store, reopen the same directory, and
  confirm every live key survived and every deleted key is still gone.
  (An in-memory-only `HashMap` wrapper with no persistence fails this
  test immediately — it's the one that proves you actually wrote to
  disk.)
- `tests/crash_recovery.rs` — truncates the data file mid-record directly
  (bypassing `Store`) and confirms reopening recovers every record before
  the cut, drops the torn one, and does not return `Err`.
- `tests/compaction.rs` — a workload of heavy overwrites and deletes,
  then `compact()`, then asserts both that the file shrank to the exact
  size the surviving live records imply *and* that every surviving key
  still reads back its correct value.
- `tests/model.rs` — a randomized test using the harness's
  `Xorshift64` PRNG to drive a deterministic sequence of put/delete/get
  operations against both the store and a `HashMap` oracle, reopening the
  store partway through, and asserting agreement at that reopen point and
  at the end.

## Estimated evenings

2–3

## Topics to read up on

- The Bitcask paper's design (keydir, append-only log, compaction) — the
  original write-up by the Riak team is the canonical description of
  exactly this architecture
- `BufReader` / `BufWriter` — why unbuffered per-record `Read`/`Write`
  calls are slow, and what buffering changes about when bytes actually
  reach the OS
- The `Seek` trait (`SeekFrom::Start`, `SeekFrom::Current`) for jumping to
  an arbitrary byte offset in an otherwise sequentially-written file
- Manual binary framing with explicit byte order (`to_le_bytes` /
  `from_le_bytes`) as an alternative to a serialization crate — what you
  gain (exact control over every byte on disk) and what you give up
  (no automatic handling of versioning or padding)
- `File::sync_all` vs `File::sync_data`, and what "flushed" vs "synced"
  actually mean at the OS/filesystem layer — why a `BufWriter::flush()`
  alone is not a durability guarantee
- FNV-1a and checksums in general — what a checksum can and cannot catch
  (a torn write vs. a deliberately corrupted file are very different
  threat models)
- `Drop` and RAII cleanup in Rust — and its sharp edge: a destructor
  cannot return a `Result`, so it can only make a best effort
- Windows vs. POSIX file-replace semantics — why deleting or renaming
  over an open file handle behaves differently on the two platforms, and
  what that means for anything that rewrites a file in place

## Off-limits

`.authoring/design.md` (at the module root) documents this task's
grading philosophy and idiom checklist — spoilers. Read it after you've
finished, if at all, same rule as every other module.
