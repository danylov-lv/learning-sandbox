`client.generate(prompt, format=...)` with `format="json"` turns on the
provider's JSON mode (Ollama's `format: "json"`), which constrains the
model to emit syntactically valid JSON but doesn't tell it what shape that
JSON should have -- you still have to describe the fields in the prompt
text itself. Passing a JSON Schema `dict` instead goes further: Ollama
passes it straight through as `format`, which constrains generation to
that exact schema (keys, types), so the model can't emit a price as a
quoted string wrapped in a currency symbol even if it wanted to.

Either way, `client.generate(...)` returns a string -- you still need
`json.loads(...)` on it before you have a dict.

Now look at what actually varies across the six snippet styles you'll see
in `data/extraction.json`: sometimes price is a clean `$23.93`, sometimes
it's inside a sentence, sometimes it's an integer number of cents with no
decimal point at all, sometimes it's in an attribute rather than visible
text. A prompt that just says "extract the price" will get the sentence
and attribute cases right most of the time from context alone -- but the
cents case needs you to spell out the conversion explicitly, because
nothing in "1535" on its own tells the model whether that's $1535.00 or
$15.35.
