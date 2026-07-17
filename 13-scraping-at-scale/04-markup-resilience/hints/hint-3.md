A concrete shape for `extract_product`, without solving the selectors for
you.

**Parse once, reuse.** Parse the HTML into a tree (whichever library you
picked) exactly once per call, then also try to locate and `json.loads` two
optional script blocks up front: any `<script type="application/ld+json">`
and any `<script id="__DATA__">` (or whatever id/type the data island
actually uses -- go look). Both may be absent (they only exist on 2 of the
4 versions) -- treat "script not found" and "json.loads failed" the same
way: you get `None` for that source, and move on to the next one in the
chain, you don't raise.

**One ordered list of candidate-extractors per field.** For each of the 7
fields, write a short ordered sequence of "try this, and if it produces
nothing useful, fall through to the next": a specific CSS selector, then an
alternate/looser CSS selector, then an `itemprop`/`meta`/`link` lookup, then
a lookup into the parsed JSON-LD dict (mind the nesting -- structured data
like this is often `{"offers": {"price": ..., "availability": ...}}`, not
flat), then a lookup into the parsed data-island dict (mind that its key
names don't have to match the field names you're returning -- check what
it's actually called), then, only as a genuine last resort, a regex over
the raw HTML text. The first source that returns something non-empty wins;
you don't need to also check the rest.

**Type coercion happens at the edge, not the source.** A `price` you pull
out of a `meta[content]` attribute or a JSON field is a string or number,
never assume which -- convert to `float` right where you extract it, and if
that conversion fails, treat it as "this source didn't produce a value,"
not as a crash. Same idea for `review_count` (some encodings give you a
bare number, one gives you a display string like `"(3)"` or `"N
reviews"` -- extracting just the digits is enough) and `in_stock` (you'll
see it spelled at least three different ways across the versions: visible
text like "In Stock"/"Out of Stock", a `schema.org` availability URL ending
in `InStock`/`OutOfStock`, and a plain JSON boolean -- normalize all of
them to an actual Python `bool`, never a string).

**Don't let a `<div class="hidden-nonce">` or an `x-nonce` meta tag anywhere
near your extraction.** It's noise the target embeds on every page (see
task 03) and irrelevant to every field this task asks for -- if your
fallback chain for any field ever touches it, that's a sign the chain is
too broad, not that you found something useful.

**Sanity-check yourself before running the validator.** Fetch the same
product id under all four `?v=1`, `?v=2`, `?v=3`, `?v=4` and confirm your
function returns the SAME values for every field each time (day/nonce
aside) -- if one version disagrees with the other three, that's the
version whose fallback chain is still missing a source.
