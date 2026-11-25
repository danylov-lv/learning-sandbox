Re-fetching every product on every run does not scale, and it is also
wasteful in a specific way: on this target, only ~4% of products actually
change between one day-snapshot and the next. Everything else you fetch is
pure overhead -- exact bytes you already had, paid for again.

The general pattern for this is content-based change detection: instead of
asking "did this resource change?" by re-fetching and re-processing it in
full, you fetch (or already have) a much cheaper SIGNAL that summarizes the
resource's current state, and only pay for full detail when that signal
disagrees with what you saw last time. A cryptographic or content hash of
the meaningful bytes is one such signal -- two fetches of an unchanged page
should hash identically; a changed page should (almost certainly) hash
differently. Real-world HTTP has a built-in version of this same idea
(`ETag` / `If-None-Match`, `Last-Modified` / `If-Modified-Since` --
conditional requests where the SERVER tells you "nothing changed" via a 304
without re-sending the body) -- this target does not implement conditional
requests, so you are building the client-side equivalent yourself: fetch,
hash, compare against what you saw last time.

The trap is what counts as "meaningful bytes." A response can differ
byte-for-byte between two fetches without the underlying DATA having
changed at all -- timestamps, request-scoped tokens, ad slot rotation, and
(on this target, deliberately) a fresh random value embedded in every single
response. A naive "hash the whole response" fingerprint will report 100% of
pages as changed, 100% of the time, which is strictly worse than useless --
it defeats the entire point of doing incremental work. Before you hash
anything, go find every place this target's responses vary from request to
request even when nothing about the product itself did, across every markup
variant it can serve. That's the actual work of this task.
