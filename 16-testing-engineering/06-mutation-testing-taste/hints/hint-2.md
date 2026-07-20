The starting suite calls each function exactly once, with a value that
sits comfortably in the middle of some branch, and checks one resulting
value. That leaves whole categories of mutation untouched:

- **Every `if`/`elif` branch that the one happy-path value never reaches.**
  `classify_price_tier` has four possible outcomes; the starting suite
  only ever observes one of them. A mutant that breaks the `"budget"` or
  `"luxury"` path can't possibly be caught by a test that never asks for
  those tiers.
- **Boundary values, exactly.** A test with `price=50.0` cannot tell the
  difference between `price < 100.0` and `price <= 100.0` -- both give the
  same answer at 50. Only a test with `price` set to exactly the boundary
  itself (e.g. `100.0`, not `99.0` or `101.0`) can distinguish `<` from
  `<=` there, because that's the one input where they disagree.
- **Error paths.** Nothing in the starting suite ever passes an invalid
  `price`, out-of-range `pct`, non-positive `weight_kg`, or malformed
  `sku`. Every validation branch (`raise ValueError(...)`, `return
  False`) is currently unexercised in the direction that actually triggers
  it.
- **Both operands of a compound condition.** `is_valid_sku` combines
  several checks with `or` inside one `if`. To pin each one down
  individually, you need a case where exactly ONE of them fails and the
  others hold -- a SKU that's invalid only because of its letter count, a
  separate one invalid only because of its digit count, and so on. A test
  that only tries a fully-valid and a wildly-invalid SKU won't distinguish
  which specific check is doing the work.

Go through `target.py` function by function and ask, for each `if`: what
value makes this condition true, what value makes it false, and have I
asserted a distinct, correct output for both?
