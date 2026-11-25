Concrete approach for the reference model inside your state machine:

- Track recency as an ordered list (or `dict`, which preserves insertion
  order in Python) of live keys, oldest-touched first. On a modeled
  `put`: if the key is new, append it and, if that pushes you over
  capacity, drop the front (oldest) entry -- from BOTH the model and by
  calling the real cache's `put`, then compare. If the key already
  existed, move it to the end (this mirrors the real cache's documented
  "a re-put refreshes recency" rule -- get this right in the model or
  you will never be able to tell the real cache's mutant m05-style bug
  apart from correct behavior). On a modeled `get`: if the key is absent
  from the model OR its recorded deadline has already passed at the
  current clock value, expect `None` and do NOT touch the model's order;
  otherwise move the key to the end (most-recently-used) and expect the
  stored value.
- Track each key's deadline as `current_clock_time + ttl` at the moment
  of `put`, recomputed on every `put` of that key (a re-put resets the
  TTL, it does not extend the old deadline).
- Treat expiry as `clock_time >= deadline` in your model to match the
  documented boundary in `src/impl.py`'s docstring -- your metamorphic
  test for the TTL boundary should assert exactly this: alive one tick
  before the deadline, gone at the deadline itself.
- For the `len()` invariant, filter your model's key set by `deadline >
  current_clock_time` before comparing counts against `len(real_cache)`
  -- do not just take `len(model_dict)`, or your model will disagree
  with a correct cache about entries that are logically expired but that
  neither side has touched yet.
- For the metamorphic properties (separate from the state machine), the
  highest-value ones to write explicitly: "put then immediate get returns
  what was put" (same clock tick), "len is always <= capacity, no matter
  what sequence of puts happened", and "a key's last successful get keeps
  it alive under LRU pressure that a stale key would not survive" -- write
  that last one as a small, hand-constructed scenario (put A, B fill the
  cache, get A, put C, assert A survived and B did not) rather than a
  `@given` property; it is exactly the shape of test that kills the
  eviction-order and recency mutants fastest and is worth having even
  though your state machine should also catch it eventually.
