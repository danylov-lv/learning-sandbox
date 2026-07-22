//! `t05-bitcask-kv-store` — a log-structured, append-only key-value store.
//!
//! This is the scaffold. Every method below ends in `todo!()`; you replace
//! the bodies. The exact on-disk format, durability contract, and
//! compaction contract this crate must implement are pinned in this task's
//! `README.md` — read it before writing any code, since there is exactly
//! one correct on-disk byte layout and the given tests check against it.
//!
//! `Store` itself is left as a unit struct here: you decide what fields it
//! needs (an open file handle, a `BufWriter`, the in-memory keydir, ...).
//! Nothing outside this crate depends on `Store`'s internal shape.

use std::io;
use std::path::Path;

/// Name of the single append-only data file inside a store's directory.
///
/// Public so tests (and the README's crash-recovery contract) can locate
/// and directly truncate the file to simulate a crash mid-write, without
/// going through the `Store` API.
pub const DATA_FILE_NAME: &str = "data.bitcask";

/// Sentinel written into a record's `value_len` field to mark a tombstone
/// (delete) record. See the README's "On-disk format" section for the
/// full record layout — this is the exact value, not a placeholder.
pub const TOMBSTONE: u32 = u32::MAX;

/// Errors this crate's public API can return.
///
/// `Io` wraps any underlying filesystem failure. `Corrupt` is available
/// for a record that fails validation in a way that is *not* the
/// "truncated trailing record" case the recovery contract handles
/// silently (see README) — the given tests never manufacture this case
/// directly, but a conforming implementation should have somewhere to put
/// it rather than panicking.
#[derive(Debug)]
pub enum Error {
    Io(io::Error),
    Corrupt(String),
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Error::Io(e) => write!(f, "io error: {e}"),
            Error::Corrupt(msg) => write!(f, "corrupt record: {msg}"),
        }
    }
}

impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Error::Io(e) => Some(e),
            Error::Corrupt(_) => None,
        }
    }
}

impl From<io::Error> for Error {
    fn from(e: io::Error) -> Self {
        Error::Io(e)
    }
}

pub type Result<T> = std::result::Result<T, Error>;

/// A single bitcask-style store, backed by one directory on disk.
///
/// Shape left to you — see the module doc comment above.
pub struct Store;

impl Store {
    /// Opens (or creates) a store rooted at `dir`.
    ///
    /// `dir` must already exist; this does not create the directory
    /// itself, only the data file inside it (`DATA_FILE_NAME`) if it is
    /// missing.
    ///
    /// On an existing data file, this replays every record from the start
    /// of the file to rebuild the in-memory keydir. Replay stops at the
    /// first record that is truncated or fails its checksum — the store
    /// then behaves as though the file ended right before that record.
    /// This must never return `Err` merely because the trailing bytes of
    /// the file are torn; it returns `Err` only for a genuine I/O failure
    /// (e.g. the directory is unreadable).
    ///
    /// After replay, the store must truncate the data file down to the
    /// last valid record boundary before accepting new writes, so that a
    /// torn tail from a previous crash never lingers behind newly
    /// appended records.
    pub fn open(dir: impl AsRef<Path>) -> Result<Self> {
        let _ = dir;
        todo!("replay the data file into a keydir, truncate any torn tail, open for appending")
    }

    /// Looks up `key` and returns its current value, or `None` if the key
    /// does not exist (or was deleted).
    ///
    /// Takes a borrowed key: looking a key up never requires the caller to
    /// give up ownership of it. Returns an owned `Vec<u8>` rather than a
    /// borrowed slice: the value lives on disk, not in memory, so there is
    /// nothing live inside `self` to borrow from — a fresh read (or a copy
    /// out of whatever in-memory buffer you keep) is the only option.
    pub fn get(&self, key: &[u8]) -> Result<Option<Vec<u8>>> {
        let _ = key;
        todo!("look up key in the keydir, seek to its recorded offset, read and validate the value")
    }

    /// Inserts or overwrites `key` with `value`, appending a new record to
    /// the data file and updating the keydir to point at it.
    ///
    /// Takes owned `Vec<u8>` for both `key` and `value`: the keydir needs
    /// to retain the key indefinitely (as a `HashMap` key, or similar), so
    /// the store is going to end up owning a copy of it one way or
    /// another — taking ownership at the call site is honest about that
    /// instead of accepting a borrow and cloning internally anyway.
    ///
    /// This does not, by itself, guarantee the write survives a crash —
    /// see the README's durability section. Call `flush` for that
    /// guarantee.
    pub fn put(&mut self, key: Vec<u8>, value: Vec<u8>) -> Result<()> {
        let _ = (key, value);
        todo!("append a framed record, update the keydir to point at the new offset")
    }

    /// Deletes `key` if present. Appends a tombstone record to the data
    /// file (deletes are themselves append-only, like everything else in
    /// this format) and removes `key` from the in-memory keydir.
    ///
    /// Deleting a key that does not exist is not an error.
    ///
    /// Takes a borrowed key: unlike `put`, delete does not need to retain
    /// the key past this call — the tombstone record written to disk owns
    /// its own copy of the key bytes independently of what the keydir
    /// does with `key` afterward.
    pub fn delete(&mut self, key: &[u8]) -> Result<()> {
        let _ = key;
        todo!("append a tombstone record, remove key from the keydir")
    }

    /// Flushes any buffered writes and syncs the data file to durable
    /// storage. After this returns `Ok`, every record appended before this
    /// call is guaranteed to survive a crash (see README).
    pub fn flush(&mut self) -> Result<()> {
        todo!("flush the writer's buffer, then sync the file to disk")
    }

    /// Returns every key currently live in the store (i.e. every key for
    /// which `get` would return `Some`). Order is unspecified.
    pub fn keys(&self) -> Vec<Vec<u8>> {
        todo!("collect the keydir's keys")
    }

    /// Number of live keys currently in the store.
    pub fn len(&self) -> usize {
        todo!("keydir size")
    }

    /// `true` if the store currently holds no live keys.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Rewrites the data file to contain only live records (dropping dead
    /// overwritten values, tombstones, and any already-reclaimed space),
    /// then atomically replaces the old data file with the rewritten one.
    ///
    /// After this returns `Ok`, every key that was live before the call
    /// reads back the same value it did before, and the data file on disk
    /// is no larger than the exact size implied by summing the pinned
    /// record framing over just the live records (see README). No key's
    /// visible behaviour changes — this is purely a disk-space and
    /// replay-time optimization.
    ///
    /// See the README's Windows note before implementing this: replacing
    /// a file that this process still holds open behaves differently on
    /// Windows than on Unix.
    pub fn compact(&mut self) -> Result<()> {
        todo!("rewrite live records into a new file, then swap it in for the old one")
    }
}

impl Drop for Store {
    /// Best-effort flush on close: a destructor cannot return a `Result`,
    /// so a failure here has nowhere to go but discarded. This is a
    /// convenience, not a durability guarantee — call `flush` explicitly
    /// wherever you actually need the guarantee.
    fn drop(&mut self) {
        let _ = self.flush();
    }
}
