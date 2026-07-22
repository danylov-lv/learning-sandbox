Build this in layers, in this order, and get each layer's own small test
passing (even an ad-hoc `main.rs`-free `#[test]` you delete later) before
moving to the next one:

1. **Framing** — writing one record's bytes to a `Vec<u8>` in memory and
   reading them back into `(key, value)`. No file, no keydir yet. Get the
   byte layout exactly right first, in isolation, where it's easy to
   inspect.
2. **Append + replay** — write records to a real file with `BufWriter`,
   then read them all back in order with `BufReader` + `Seek`, rebuilding
   a `HashMap` as you go. Still no `Store` API, just "can I write N
   records and replay all N back."
3. **The `Store` API** — wire `open`/`put`/`get`/`delete`/`flush` around
   what you built in steps 1–2, tracking byte offsets in the keydir so
   `get` can seek directly instead of replaying.
4. **Torn tails** — deliberately write a short/garbage tail after some
   good records (in a scratch test, before you trust the real test suite)
   and confirm replay stops cleanly instead of panicking or erroring.
5. **Compaction** — last, since it depends on everything above already
   being correct.

Don't try to design the `Store` struct's fields before step 1. You'll
know what you need (a file handle? two? a byte-offset cursor?) once
you've actually written and re-read a record by hand.

Think about *why* the keydir stores an offset into the file at all,
rather than the store just keeping every value in memory. What would
break if it did?
