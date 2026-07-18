Structure it as two nested layers around a single "get one response" call:

- The INNER layer handles ONE ask: call `generate()`, and if it raises
  `TransientError`, sleep for a backoff that grows with the attempt
  number, then try again -- up to `max_retries` extra times. Any
  exception that isn't a `TransientError` should NOT be caught here; let
  it propagate straight out. If the retry budget runs out, let the last
  `TransientError` propagate out too -- that's the signal to the outer
  layer that this client is done.
- The OUTER layer handles reasking: it calls the inner layer to get one
  response, then tries to `json.loads` it and validate it against
  `schema`. If that all succeeds, return the parsed dict -- done. If it
  fails and there's reask budget left, build a new prompt (original
  prompt + something describing what went wrong) and go around again. If
  it fails and the reask budget is gone, that client has failed outright.
  If the inner layer's exception propagated instead (retry budget
  exhausted), that ALSO counts as the client failing outright, without
  spending any reask attempts on it.

`structured()` itself is then: run the two-layer thing against `primary`;
if it fails outright and there's a `fallback`, run the exact same
two-layer thing against `fallback` starting from the original prompt, and
let whatever THAT produces (success or failure) be the final answer.

For `schema`: check whether it's a `dict` or something callable
(`callable(schema)`) and branch. Keep the two validation paths as
separate small functions -- you'll call whichever one applies from inside
the outer layer, and its return should tell you both "valid or not" and,
if not, the error text to feed into the next reask prompt.
