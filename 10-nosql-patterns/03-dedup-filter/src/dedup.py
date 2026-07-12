"""s10.t03 -- exact SET dedup vs probabilistic Bloom-filter dedup.

A scraper needs to answer "have I seen this url before?" on every hit. Two
ways to answer it, same shape from the caller's side (`add_if_new(url) ->
bool`), very different cost profiles:

  * `SetDedup` -- a Redis `SET`. Exact: `SADD`'s return value already tells
    you whether the member was new, atomically, no race to worry about. Cost:
    every distinct url you've ever seen lives in memory, forever, and the
    set grows without bound as the crawl grows.
  * `BloomDedup` -- a RedisBloom Bloom filter (`BF.*`). Approximate: sized
    once via `capacity` and `error_rate` at creation time, its memory
    footprint does not grow per-item the way a SET's does. The price is an
    asymmetric error mode -- read both docstrings below carefully, the
    asymmetry is the entire point of this task.

Both classes must confine every Redis key they touch under `s10:t03:`
(the shared Redis instance is namespaced per task -- see harness/common.py).

RedisBloom via redis-py: a connected `redis.Redis` client exposes the
`BF.*` command family through `client.bf()`, e.g.
`client.bf().reserve(key, error_rate, capacity)` and
`client.bf().add(key, item)`. You can also issue the raw commands yourself
via `client.execute_command("BF.RESERVE", key, error_rate, capacity)` /
`client.execute_command("BF.ADD", key, item)` if you prefer -- both reach the
same module commands. Either way, mind `decode_responses`: if the client was
constructed with `decode_responses=True` you'll get back `str`/`bool`-ish
Python values; with `decode_responses=False` you'll get raw `bytes` and may
need to decode command replies yourself.
"""


class SetDedup:
    """Exact url dedup backed by a single Redis SET.

    Every url ever passed to `add_if_new` becomes (and remains) a member of
    the set at `key`. There is no forgetting and no approximation: this
    structure can tell you, with certainty, whether it has seen a given url
    before. The cost of that certainty is memory that grows with every new
    distinct url -- there is no cap, no configurable tradeoff. At the scale
    of a real crawl (tens of millions of distinct urls) that's a real memory
    line item, and it never shrinks.
    """

    def __init__(self, client, key: str):
        """
        Args:
            client: a connected `redis.Redis` (see `harness.common.redis_client`).
            key: the Redis key for the backing SET. Must live under
                `s10:t03:` (e.g. `"s10:t03:seen-urls:set"`).
        """
        self.client = client
        self.key = key

    def add_if_new(self, url: str) -> bool:
        """Record `url` as seen and report whether it was new.

        Returns:
            True iff `url` was NOT already a member of the set (i.e. this
            call just added it for the first time). False if `url` was
            already present. This must be exact -- no false positives, no
            false negatives, ever -- which a single atomic `SADD` already
            gives you for free via its own return value (the number of
            elements actually added).
        """
        raise NotImplementedError


class BloomDedup:
    """Approximate url dedup backed by a RedisBloom Bloom filter.

    A Bloom filter is a fixed-size bit array plus a handful of hash
    functions. Adding an item sets some bits; checking membership means
    checking whether all of those bits are already set. That design gives it
    a very specific, ASYMMETRIC error profile -- understanding this asymmetry
    is the whole point of the task:

      * FALSE POSITIVE (possible): the filter can claim an item is "already
        present" when it is genuinely new, if some unlucky combination of
        other items already set all the bits that item's hashes land on.
        Concretely for this task: the scraper wrongly treats a brand-new url
        as a duplicate and SKIPS it. This happens at roughly the configured
        `error_rate`, by design -- it's the price paid for fixed memory.
      * FALSE NEGATIVE (structurally impossible): the filter can NEVER claim
        an item is "new" if it was in fact already added. Every bit that was
        set when that item was added is still set (bits are only ever set,
        never cleared by an add), so its membership check can only ever
        succeed. Concretely: the scraper will never re-crawl a url it has
        genuinely already seen because of a Bloom filter mistake.

    That's why a Bloom filter is a reasonable dedup structure for a crawler,
    even though it's "wrong" sometimes: the only way it's ever wrong is by
    missing a new page occasionally, tuned to a rate you chose up front --
    never by wasting a re-crawl on something already done.
    """

    def __init__(self, client, key: str, *, capacity: int, error_rate: float):
        """
        Args:
            client: a connected `redis.Redis`.
            key: the Redis key for the backing Bloom filter. Must live under
                `s10:t03:` (e.g. `"s10:t03:seen-urls:bloom"`).
            capacity: the number of items you expect to add. RedisBloom sizes
                the underlying bit array from this (and `error_rate`) at
                reservation time -- get this roughly right; the whole appeal
                of a Bloom filter is a memory footprint fixed at creation
                time rather than one that grows per item the way a SET's
                does.
            error_rate: the target false-positive probability once the
                filter holds `capacity` items (e.g. 0.01 for ~1%). Smaller
                `error_rate` costs more memory for the same `capacity` --
                that trade is set explicitly here, not discovered by
                surprise later.
        """
        self.client = client
        self.key = key
        self.capacity = capacity
        self.error_rate = error_rate

    def ensure(self):
        """Create the Bloom filter at `self.key` via `BF.RESERVE` if it does
        not already exist, using `self.capacity` and `self.error_rate`.

        Must be safe to call more than once (e.g. don't blow up if the key
        already exists -- check first, or handle the "already exists" error
        from a repeat `BF.RESERVE`). Called before any `add_if_new`.
        """
        raise NotImplementedError

    def add_if_new(self, url: str) -> bool:
        """Add `url` to the Bloom filter and report whether it believes
        `url` is new.

        Returns:
            Whatever `BF.ADD` reports: True if the filter believes this is
            the first time it's seen `url`, False if it believes `url` was
            already added. As documented on the class: a False for a
            genuinely-new url (false positive) is possible, at roughly
            `error_rate` -- but a True for a url that was already added
            (false negative) is not possible.
        """
        raise NotImplementedError
