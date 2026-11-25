The decode, as a sequence of steps, no code:

1. Base64-decode the string. You get back a small run of raw bytes -- the
   two's-complement big-endian representation of a (possibly negative, but
   never for a price) integer. This is exactly the same byte layout a
   two's-complement fixed-width integer would have in memory, just
   variable-length and MSB-first.
2. Turn those bytes into a Python integer that respects the sign bit --
   Python's own integer-from-bytes conversion has a flag for exactly this
   ("signed"); without it you'd get the wrong (always non-negative) value
   for anything that happens to encode with its top bit set.
3. That integer is the UNSCALED value -- i.e. the real price already
   multiplied by `10**scale` and rounded. Divide it back down by `10**scale`
   to recover the actual decimal value. Do this division in a way that
   stays exact (there's a decimal type built for exactly this, and it can
   construct a value directly from an integer plus a power-of-ten shift --
   look for the method on it that shifts the decimal point without ever
   going through binary floating point).

For the op tally: `change_op(payload)` already gives you the `op` string
directly (`"r"`, `"c"`, `"u"`, `"d"`) -- you don't need to inspect anything
else to know which bucket an event belongs to. An upsert keyed on `op`
that starts a row at `n=1` and otherwise increments the existing row's `n`
is all `ops.t02_change_summary` needs; there's no need to keep counts in
Python memory across messages since the table itself is the running total
and this script's job is to replay the whole topic into it once per run.
