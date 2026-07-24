# Hint 2

Four functions, four distinct problems:

- `clean_price` and `batch_normalize` — no annotations at all. Strict
  mode's `disallow_untyped_defs` rejects a function with no parameter or
  return annotations. Add them; the types are exactly what the body
  already assumes.
- `parse_optional_tag` — the parameter accepts `None` (that's the default
  value) but isn't typed to allow it, and the body never checks for it
  before calling a string method. Two fixes needed, not one: the
  annotation, and a guard.
- `to_currency_code` — declared `-> str`, but one branch returns `None`.
  Strict mode won't let a function silently disagree with its own
  signature. Look at what `test_to_currency_code_invalid_raises` expects
  it to do instead of returning `None`.
