Build one prompt per record that includes: the literal list of the 8
`CATEGORIES` strings, the record's `title` and `description`, and an
instruction to respond with a single JSON object containing `"category"`
and `"brand"`. Use `client.generate(prompt, format="json", temperature=0.0)`
(or `format={"type": "object", ...}` as a JSON-schema dict, or `.chat`
with a system message) so the response is a JSON string you can
`json.loads` directly, rather than free text you have to regex a category
name out of.

Consider telling the model explicitly that some words in the title or
description may be misleading or off-topic (without naming the exact
generation mechanism) -- an instruction like "judge the category of the
actual physical product, not just individual words in the text" nudges the
model away from a pure keyword match and toward the kind of holistic
judgment a keyword lookup can't do.

Normalize the category string the model returns (`.strip().lower()`)
before you use it -- don't assume it comes back byte-identical to the
`CATEGORIES` list's casing/spacing every time.

Wrap the JSON parse in a `try`/`except` and have a fallback path (e.g. a
regex to pull out the first `{...}` blob, or a default/empty result) so
one bad response out of 80 doesn't take down the whole run.
