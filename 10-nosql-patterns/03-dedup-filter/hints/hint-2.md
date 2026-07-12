A Bloom filter is a fixed-size bit array plus several hash functions. Adding
an item hashes it a few ways and sets those bits. Checking an item hashes it
the same ways and checks whether all those bits are already set. Sit with
what that implies for each direction of "wrong":

- Can it ever say "new" for something it already added? Think about what
  adding does to the bits (only ever sets them, never clears them) and what
  checking does (only ever reads them). Once an item's bits are set, can a
  later check for that SAME item ever come back false? That's why false
  negatives can't happen here -- it isn't a tuning choice, it falls out of
  how the structure works.
- Can it say "already seen" for something genuinely new? Think about what
  happens when a handful of OTHER items happen to have already set all the
  bit positions that some new item's hashes would also land on. Nothing
  distinguishes "this item set these bits" from "some combination of other
  items happened to set all these bits already" -- the filter has no way to
  tell. That's the false positive, and it's why the filter needs an
  `error_rate` knob at all: you're choosing how often that unlucky collision
  is allowed to happen.

`BF.RESERVE key error_rate capacity` is where you spend that choice: `capacity`
is roughly how many distinct items you expect to add, `error_rate` is the
false-positive probability you're willing to tolerate once the filter holds
that many items. Both feed directly into how large a bit array RedisBloom
allocates -- get `capacity` badly wrong (too low) and your real false-positive
rate will drift well above what you configured.

`BF.ADD key item` returns whether the item was newly added (same shape as
`SADD`'s return, conceptually) -- that return value is your `add_if_new`
answer, same as with the SET. In redis-py, reach it via `client.bf().add(...)`
or `client.execute_command("BF.ADD", ...)`; `client.bf().reserve(...)` /
`execute_command("BF.RESERVE", ...)` for `ensure()`. Check whether the key
already exists before reserving again, or be ready to catch what a repeat
`BF.RESERVE` does.
