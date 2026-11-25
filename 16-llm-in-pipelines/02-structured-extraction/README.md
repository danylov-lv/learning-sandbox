# 02 -- Structured Extraction

## Backstory

A teammate scraped 50 product listings from six different storefront
templates and handed you the raw HTML with a straight face: "just write a
CSS selector for the price." You open the first snippet and the price is
in a `<span class="amt">` -- fine, generic but workable. The second has no
price element at all, just a sentence: "Now only $30.69 -- Ships today."
The third puts everything in `data-*` attributes and repeats only the name
in visible text. The fourth is riddled with `&nbsp;` and ragged
indentation. The fifth has unclosed `<b>` and `<p>` tags and no closing
`</ul>` -- an HTML parser in strict mode throws on it. The sixth writes
the price as an integer number of cents, `data-price-cents="1535"`, no
decimal point anywhere, and never states availability except through
which of two mutually-exclusive buttons happens to be present.

A selector chain that handles template one breaks on template two. A
selector chain that handles all six starts to look less like a scraper and
more like a small, brittle parser for six different micro-languages you'd
have to maintain forever. This is the case for reading raw HTML text with
an LLM instead: it doesn't care which template it's looking at, because it
isn't walking a DOM tree looking for a specific tag -- it's reading text
and understanding what a price, a brand, and a stock signal look like in
context.

## What's given

- `data/extraction.json` -- 50 gold-STRIPPED HTML snippets, each
  `{snippet_id, html}`. Generate it first if you haven't:
  `uv run python generate.py` from the module root.
- `harness/llm.py` -- the provided, swappable LLM client. Call
  `harness.llm.get_client()` to get one; it defaults to a local Ollama
  server on port 11439 running `qwen2.5:7b-instruct`. `client.generate(prompt,
  *, format=None, temperature=0.0)` returns the model's text response;
  `format="json"` asks the provider for JSON-mode output, or pass a JSON
  Schema `dict` for constrained structured output (Ollama and OpenAI both
  accept this via `harness.llm`'s uniform interface).
- `harness/common.py` -- `norm_price` (parses `$23.93`, `23,93`, `"1535"`,
  European `1.299,00` grouping, etc. into a float) and `norm_text`
  (lowercase/strip-punctuation loose string normalization), used by the
  validator to grade your output.
- `src/extract.py` -- the scaffold you implement. One function,
  `extract_fields(html, client) -> dict`, with a docstring spelling out the
  exact return contract.

## What's required

Implement `extract_fields(html, client)` in `src/extract.py`. It must:

1. Send the raw `html` to the model via `client.generate(...)` (or
   `client.chat(...)`), with a prompt you design that explains the fields
   to extract and the edge cases (price as integer cents, price stated
   only in prose, stock only implied by button presence, etc.).
2. Use `format="json"` or a JSON-schema dict so the response is reliably
   parseable JSON.
3. Return a `dict` with exactly the keys `name`, `brand`, `price`,
   `currency`, `in_stock` -- see the docstring in `src/extract.py` for the
   expected type/shape of each.

You're free to write a small runner script of your own to loop over
`data/extraction.json` and eyeball your own accuracy while iterating --
the validator does its own independent loop and does not use anything you
write beyond `extract_fields` itself.

## Completion criteria

From the module root:

```bash
uv run python 02-structured-extraction/tests/validate.py
```

The validator calls `require_client()` first (so an unreachable Ollama
server is reported as an actionable infra message, never a confusing
metric failure), then calls your `extract_fields(html, client)` once per
snippet in `data/extraction.json` and grades each of the 5 fields
independently against gold (reconstructed in-memory from `generate.py`,
never read back from the stripped data file):

- `price`: your value is parsed with `norm_price` and compared to gold
  with a small absolute tolerance.
- `currency`: exact match after uppercasing.
- `in_stock`: exact boolean match.
- `name` / `brand`: a loose match -- normalized exact equality, or strong
  token overlap with gold's normalized tokens (see `src/extract.py`'s
  docstring and the validator for specifics) -- exact string
  reproduction is not required.

Prints `PASSED` with the per-field accuracy over all 50 snippets, or
`NOT PASSED: <reason>` and exits 1 -- including while `src/extract.py` is
still unimplemented (`NotImplementedError` surfaces as a clean message, no
traceback).

## Estimated evenings

1

## Topics to read up on

- Prompting an LLM for structured/JSON output, and why a JSON Schema or a
  provider's native JSON mode beats asking for JSON in plain prose
- Why "read the raw text" generalizes across markup variation in a way a
  CSS-selector or XPath chain doesn't -- and where that tradeoff (cost,
  latency, occasional misparse) is and isn't worth it versus a
  selector-based scraper
- Normalizing loosely-formatted numeric/currency strings into a comparable
  type (this module's `harness.common.norm_price` is one example
  implementation worth reading)
- Designing a prompt that explicitly calls out edge cases in the data
  (a value encoded as an attribute rather than visible text, a price
  denominated in cents rather than decimal currency) rather than assuming
  a model will infer them unprompted

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API
contract, the exact dataset generation process (including which of the six
HTML templates exist and how gold values are drawn), and this task's
verification margins -- spoilers. Don't read it before finishing this task.
