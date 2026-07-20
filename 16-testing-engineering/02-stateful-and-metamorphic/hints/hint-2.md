`hypothesis.stateful.RuleBasedStateMachine` is the mechanism. Shape:

- `__init__`: build the real `TTLCache` (with your mutable-box clock) and
  your reference model's initial empty state, both as instance attributes.
- One `@rule(...)` method per operation the cache supports: `put`,
  `get`, and `advance_clock`. Each `@rule` takes Hypothesis strategies as
  arguments (e.g. `@rule(key=st.integers(0, 5), value=st.integers())`) --
  a small, DELIBERATELY narrow key space (say 5-10 distinct keys) matters
  more here than it sounds: with a tiny capacity and a tiny key universe,
  Hypothesis is forced to generate sequences that repeatedly collide,
  evict, and re-touch the same handful of keys, which is exactly the
  traffic pattern that exposes recency and eviction bugs. A huge random
  key space mostly generates sequences where nothing ever collides.
- Consider using a `Bundle` if you want rules to only operate on
  "keys known to have been put" rather than blindly guessing keys --
  optional, a fixed small `st.sampled_from([...])` key space works fine
  too and is simpler to reason about.
- Each rule updates BOTH the real cache and your reference model the same
  way, in the same method (that is what keeps them in sync so you can
  diff them).
- One or more `@invariant()` methods run after every rule application
  and assert the real cache agrees with the model: same live keys, same
  values, same `len()`. This is where a bug actually gets caught -- the
  invariant fails on whatever step first causes disagreement, and
  Hypothesis shrinks the rule sequence down to a minimal reproduction.
- `advance_clock` should only ever move time FORWARD (Hypothesis'
  `st.floats` or `st.integers` with a `min_value` of a small positive
  number is enough) -- going backward in time is not a scenario this
  cache needs to handle correctly, and generating it just adds noise.

Finish by assigning the generated `TestCase` to a module-level name so
pytest collects it: `TestCacheStateMachine = YourClassName.TestCase`.
