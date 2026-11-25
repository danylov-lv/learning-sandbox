Concrete shape, without writing the hashing/fetching for you.

**Finding every nonce position.** Fetch the same product id 4 times with
`?v=1`, `?v=2`, `?v=3`, `?v=4` and diff each pair of responses by eye (or
`difflib`) -- everything that differs between two fetches of the identical
`?day=`/`?v=` is, by construction on this target, either the nonce or
whitespace/ordering noise from your own tooling. Do the same once more for
`GET /api/product/{id}` (JSON, one shape, no `?v=`). That gives you an
exhaustive list of exactly five places to handle -- don't guess, verify by
diffing actual responses.

**If you strip-then-hash the raw text:** a small ordered list of
`(pattern, replacement)` pairs -- one per markup version's nonce shape, one
for the JSON `_nonce` key -- applied before you hash, is enough; you do not
need a general-purpose HTML sanitizer. Regex on the exact tag/attribute
shape (e.g. the `content="..."` value inside the specific `<meta
name="x-nonce">` tag, not "any uuid-looking substring anywhere") is safer
than a bare UUID-pattern match, since a UUID-shaped value could in principle
appear elsewhere. After stripping, hash with something in the standard
library (`hashlib.sha256(text.encode()).hexdigest()` or similar) -- you do
not need anything fancier than a standard cryptographic hash here.

**If you extract-then-hash a structure:** build a plain dict of just the
fields you care about, serialize it DETERMINISTICALLY (e.g.
`json.dumps(d, sort_keys=True)`) before hashing -- dict key order and float
repr are both sources of accidental nondeterminism that would make an
otherwise-unchanged record hash differently between two runs for reasons
that have nothing to do with the nonce.

**`changed_between`.** The cleanest shape: call `build_fingerprint_index`
for `day_prev` and again for `day_curr` over the same `product_ids`, then
`{pid for pid in product_ids if idx_prev[pid] != idx_curr[pid]}`. Fetching
both days inside the same call is the simplest correct version; treating a
previously-built `day_prev` index as reusable (skip re-fetching it) is an
optimization you can add once the simple version passes.

**Pacing.** Reuse whatever bounded-concurrency + measured-elapsed-time
pacing approach you used (or will use) for task 01 -- this target's rate
limiter (capacity=25, refill 50/s) punishes bursts, not a steady ~40-45
req/s. A plain sequential loop with no concurrency at all is also fine here
if you don't mind it being slower; correctness, not speed, is what the
validator checks.
