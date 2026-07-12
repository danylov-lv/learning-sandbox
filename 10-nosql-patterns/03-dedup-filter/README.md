# 03 -- Dedup Filter: Exact SET vs Bloom Filter

## Backstory

Your scraper has been running for months. Every scrape hit produces a url,
and before the worker bothers fetching it, it needs to answer one question:
"have I already seen this url?" Re-scraping something you already have is
wasted bandwidth and wasted downstream processing -- at the scale this
crawl is aiming for (tens of millions of urls, growing every day), that
waste compounds fast.

The obvious answer is a Redis `SET`: `SADD seen_urls <url>`, and `SADD`'s own
return value tells you whether it was new. This is exact -- zero false
positives, zero false negatives, ever. But it is not free: every distinct
url you've ever seen sits in memory, in full, forever. Tens of millions of
urls (each maybe 40-80 bytes, plus Redis's per-member overhead) becomes a
serious memory line item, and it only grows.

A **Bloom filter** trades exactness for a fixed, tiny memory footprint. You
tell it up front roughly how many items you expect (`capacity`) and how
often you're willing to be wrong (`error_rate`), and it allocates a bit
array sized for that budget -- not one that grows with every new url. The
catch is the asymmetry in HOW it can be wrong:

- It can produce a **false positive**: claim a url is "already seen" when it
  is actually brand new. Consequence here: the scraper wrongly *skips* a new
  url. You lose that one page, silently, at roughly the rate you configured.
- It can **never** produce a **false negative**: if the filter says "seen
  before, skip it not-new", it is telling the truth -- you did add that item
  at some point. It will never make you re-crawl something you've already
  scraped by mistakenly calling it new.

That asymmetry is the whole point of this task. A false positive (missing a
new page occasionally) is a tolerable, tunable cost for a crawler. A false
negative (thinking you've never seen a url you actually have, and
re-crawling it) would be a correctness bug -- and Bloom filters structurally
cannot do that. This task has you build both, side by side, and prove the
tradeoff with your own eyes: the accuracy Redis's `SET` gives you for free,
the memory it costs; and the memory RedisBloom gives you for a small,
bounded, tunable error rate.

## What's given

- `src/dedup.py` -- two class stubs, `SetDedup` and `BloomDedup`, sharing the
  same `add_if_new(url) -> bool` shape so they're interchangeable from the
  caller's point of view. Rich docstrings spell out exactly what each method
  must guarantee, including the FP/FN asymmetry. Bodies currently
  `raise NotImplementedError`.
- The live stack: Redis on `localhost:6310` (`redis/redis-stack-server`,
  RedisBloom's `BF.*` commands already loaded -- `harness.common.redis_client`
  connects for you). No password.
- `data/events.json` (NDJSON, gitignored, already generated) -- a stream of
  scrape events, each carrying a `url`. About 30% of the stream re-scrapes a
  url already seen earlier in the stream; the rest are first sightings.
- `data/ground-truth.json` (committed) -- `events.unique_urls` is the exact
  count of distinct urls in the stream; `events.duplicate_events` is the rest.
- `harness/common.py` -- `redis_client()`, `redis_flush_prefix()`, and
  `load_ground_truth()`.

## What's required

Implement both classes in `src/dedup.py`:

1. **`SetDedup(client, key)`** -- `add_if_new(url)` returns `True` iff `url`
   had never been added before (i.e. it was genuinely new), `False` if it was
   already a member. Backed by a single Redis `SET` at `key`. This must be
   exact: `SADD`'s own return value already tells you this, with no
   read-then-write race to worry about.
2. **`BloomDedup(client, key, *, capacity, error_rate)`** -- `ensure()`
   creates the Bloom filter via `BF.RESERVE` if it doesn't already exist
   (safe to call more than once). `add_if_new(url)` returns whatever
   `BF.ADD` reports: `True` if the filter believes `url` is new, `False` if
   it believes `url` was already added. It may occasionally return `False`
   for a url that is genuinely new (a false positive, at roughly
   `error_rate`) -- but it must never return `True` for a url it already
   added (no false negatives, ever; that's a structural Bloom filter
   guarantee, not something you need to code defensively against).

Both classes must confine every key they touch under the prefix `s10:t03:`
(the Redis instance is shared across the whole module).

## Completion criteria

Run, from the `10-nosql-patterns` directory:

```bash
uv run python 03-dedup-filter/tests/validate.py
```

It:

1. Resets the `s10:t03:` namespace, then feeds the full event stream's urls
   (in order) through a fresh `SetDedup`. Asserts the number of `True`
   results equals `ground-truth.json`'s `events.unique_urls` **exactly** --
   zero false positives, zero false negatives.
2. Feeds the same stream through a fresh `BloomDedup` (reserved with
   `capacity >= unique_urls` and a small `error_rate`), then feeds every
   *distinct* url through it a second time. Asserts **none** of that second
   pass reports `True` -- zero false negatives.
3. Checks the Bloom filter's count of `True` results on the first pass (its
   estimate of how many urls were unique) lands close to, but at or below,
   the true unique count -- within a small multiple of the configured
   `error_rate`, proving the false-positive rate is in the ballpark you
   configured, not wildly off.
4. Compares `MEMORY USAGE` of the `SET` key against the Bloom key after both
   have absorbed the same urls, and asserts the Bloom key uses **strictly
   less** memory. Reports both byte counts in the `PASSED` message.

`NOT PASSED: <reason>` and exit 1 on any failure, including a stub still
raising `NotImplementedError`, the stack being down, or RedisBloom not being
loaded.

## Estimated evenings

1

## Topics to read up on

- Exact set membership (`SADD`/`SISMEMBER`) vs probabilistic membership
  (Bloom filters) -- what each structure actually guarantees
- Bloom filter false positives vs false negatives: why one is possible and
  the other is structurally impossible, and why that specific asymmetry is
  what makes Bloom filters usable for dedup at all
- `BF.RESERVE`'s two knobs, `capacity` and `error_rate`, and what happens
  (gradually rising false-positive rate, or automatic sub-filter scaling
  depending on configuration) when you exceed the reserved capacity
- `BF.ADD` vs `BF.EXISTS` -- what each returns and when you'd reach for one
  over the other
- `MEMORY USAGE <key>` -- how to read it as a proxy for "what does this
  structure actually cost", and why a Bloom filter's memory is roughly fixed
  by `capacity`/`error_rate` while a `SET`'s grows with every distinct member
- The general space/accuracy tradeoff probabilistic data structures make,
  and when it's worth taking (hint: it's a function of how many distinct
  items you expect and how expensive a rare false positive actually is)

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, and design rationale for every task in this module -- spoilers.
Don't read it before finishing this task.
