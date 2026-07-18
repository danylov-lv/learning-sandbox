No ready-made code here -- just the concrete shape.

Build a JSON Schema dict describing an object with five properties:
`name` (string), `brand` (string), `price` (number), `currency` (string),
`in_stock` (boolean), all required. Pass it as `format=` to
`client.generate(...)`.

Write a prompt that includes the raw `html` verbatim and, in plain
language, explains each field plus the two trickiest edge cases in this
dataset:

- "If the price is expressed as an integer number of cents (for example in
  a `data-price-cents` attribute, with no decimal point anywhere), divide
  by 100 to get a normal decimal price."
- "in_stock should be true if the listing shows the item is available to
  buy right now (an explicit in-stock phrase, a truthy stock attribute, or
  an 'Add to Cart' button) and false if it shows the item is unavailable
  (an out-of-stock phrase, a falsy stock attribute, or an 'unavailable'
  marker instead of a buy button)."

Call `client.generate(prompt, format=schema, temperature=0.0)`, then
`json.loads(...)` the returned string into a dict and return it directly
(or after minor key renaming, if your prompt used different key names
internally) -- the validator expects exactly the five keys named in the
`src/extract.py` docstring.

If a particular snippet's response ever fails to parse as JSON, that's a
real failure mode worth thinking about (a 7B model given a hard/unusual
snippet occasionally emits something malformed) -- but with `format=` set
to a schema and `temperature=0.0`, this should be rare enough not to need
handling on your own for this task specifically (task 01's resilience
wrapper is where retry-on-invalid-JSON belongs, if you want to reuse it
here).
