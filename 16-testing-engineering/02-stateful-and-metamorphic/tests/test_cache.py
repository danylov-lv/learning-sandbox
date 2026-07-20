"""Learner-authored test suite for `src.sut.TTLCache`.

This file is a SCAFFOLD, not a solution -- as shipped it defines no test
functions at all, so `uv run python tests/validate.py` fails cleanly
(0 collected). Your job is to fill it in.

Import the cache under test like this, never `from src.impl import ...`:

    from src.sut import TTLCache

You need TWO complementary kinds of tests. Neither alone is enough --
`validate.py` grades you by whether your suite kills every mutant in the
(hidden) mutant bank, and different mutants are only observable through
different lenses.

1. A Hypothesis STATEFUL test (`hypothesis.stateful.RuleBasedStateMachine`)
   that drives `put`/`get`/advancing-the-clock against a small reference
   model (e.g. a plain dict tracking key -> (value, insertion-or-touch
   order, expiry deadline)) and asserts the real cache agrees with the
   model after every step. This is what catches eviction-order and
   recency bugs -- the kind of bug that only shows up after a SEQUENCE of
   operations, not from any single call in isolation.

   Sketch:

       from hypothesis.stateful import RuleBasedStateMachine, rule, invariant
       from hypothesis import strategies as st

       class CacheModel(RuleBasedStateMachine):
           def __init__(self):
               super().__init__()
               self.clock_value = 0.0
               self.cache = TTLCache(capacity=..., ttl=..., clock=lambda: self.clock_value)
               # ... reference model state here ...

           @rule(...)
           def put(self, ...):
               ...

           @rule(...)
           def get(self, ...):
               ...

           @rule(...)
           def advance_clock(self, ...):
               self.clock_value += ...

           @invariant()
           def len_matches_model(self):
               ...

       TestCacheStateMachine = CacheModel.TestCase

   `TestCacheStateMachine` (a plain `unittest.TestCase` subclass Hypothesis
   generates for you) is what pytest actually collects and runs -- assign
   it to a module-level name pytest can find.

2. A few METAMORPHIC / property tests (plain `@given(...)` Hypothesis
   tests, no state machine needed) that check specific relations hold
   no matter the input, e.g.:
     - `get` called immediately after `put(key, value)` (same clock tick)
       returns `value`.
     - `len(cache)` never exceeds the configured `capacity`.
     - a key put at time t with ttl T is definitely gone (get returns
       None) by the time the clock reaches `t + T`.
     - a `get` that misses never changes what the cache would report for
       any other key.

USE THE INJECTED `clock` PARAMETER. Never call `time.sleep()` in a test --
construct `TTLCache(..., clock=lambda: current[0])` (a mutable closure
over a list/box you control) or similar, and advance time by just
reassigning the box. That is the entire point of the clock being
injectable: deterministic, instant, reproducible tests.
"""

from __future__ import annotations

# TODO: from src.sut import TTLCache
# TODO: import hypothesis / hypothesis.strategies / hypothesis.stateful as needed

# TODO: write a RuleBasedStateMachine driving put/get/advance-clock against
#       a reference model, and assign its .TestCase to a module-level name,
#       e.g.:
#           TestCacheStateMachine = YourStateMachine.TestCase

# TODO: write metamorphic/property tests for TTL, capacity, and recency
#       relations described in the module docstring above.
