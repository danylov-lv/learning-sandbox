The connector's `decimal.handling.mode` defaults to `precise` (this task's
validator does not override it). Under `precise`, Kafka Connect represents
a `NUMERIC`/`DECIMAL` column using its `Decimal` logical type, which
serializes -- via the JsonConverter, schemas enabled -- as a base64 string.
That string is not the number's text form; it's the base64 encoding of the
UNSCALED value's bytes, two's-complement, big-endian.

"Unscaled" means: take the real value, multiply by `10**scale`, round to an
integer -- that integer is what got encoded. The `scale` itself is not
carried in the payload value; it lives on the *field's schema* (the
`"schema"` half of the envelope that `decode_value()` already stripped
off). For `shop.offers.price`, the column is `NUMERIC(12, 2)`, so its scale
is fixed at 2 -- that's why the scaffold hands you `PRICE_SCALE = 2` as a
constant instead of asking you to parse it out of the schema at runtime.

There IS an escape hatch: set `decimal.handling.mode=double` or `=string`
on the connector, and you'd get a plain JSON number or a decimal string
instead of this base64 blob. The validator deliberately does not use it --
decoding the `precise` encoding by hand is the actual point here.
