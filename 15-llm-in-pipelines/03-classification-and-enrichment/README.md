# 03 -- Classification and Enrichment

## Backstory

A catalog feed lands on your desk with 80 records that need a category tag
before they can be routed into the right storefront section, plus a brand
field pulled out for a faceted-search filter. There's no training data and
no time to build one -- just titles and short marketing descriptions,
written by whoever scraped or exported the feed, with no guarantee the
wording reliably signals the category. A teammate's first instinct was a
keyword lookup: match a known brand to its usual department, match a noun
in the title to a department's typical products. It works most of the
time, and then quietly doesn't -- a "cookbook" that's shelved as an
electronics accessory bundle, a listing whose brand name is a
category-agnostic house label, a description that name-drops an unrelated
hobby because that's what the copywriter's template did that day.

This task swaps the keyword lookup for a 7B instruct model: give it the
record, give it the closed set of valid categories, and ask it to reason
about what the product actually is, brand included. It won't be perfect --
nothing looking at eight words of marketing copy would be -- but it should
clearly beat a lookup table on records built specifically to fool one.

## What's given

- `data/classification.json` -- 80 records, each
  `{record_id, title, description}`. No category or brand label; that's
  what you're producing.
- `harness/llm.py` -- the provided, provider-agnostic `LLMClient`
  (`get_client()`, `.generate(prompt, *, system=None, format=None,
  temperature=0.0, options=None)`, `.chat(messages, *, format=None,
  temperature=0.0)`). Use it as-is; do not reach for a provider SDK
  directly.
- `harness/common.py` -- `require_client()` (checks Ollama/OpenAI is
  reachable before any live call), `macro_f1`, `norm_text`, and the
  `PASSED`/`NOT PASSED` validator plumbing.
- `src/classify.py` -- the scaffold. `CATEGORIES`, the closed 8-value label
  set, is already defined there:

  ```
  electronics, home-goods, kitchen, toys, sporting-goods, apparel, books, garden
  ```

  `classify_record(title, description, client) -> dict` is the one
  function you implement; its docstring spells out the exact contract.

## What's required

Implement `classify_record` in `src/classify.py`. It must:

- Call the model through `client` (an `LLMClient`), with a prompt you
  design. The prompt must state the closed category list explicitly --
  the model has no other way to know this project's exact 8 labels.
- Return `{"category": <one of the 8 CATEGORIES values>, "brand": <the
  brand token as it appears in the title>}`.
- Not crash on a single malformed model response -- handle a response that
  isn't valid JSON defensively, since the validator calls this function
  once per record across all 80 records in one run.

You choose the prompt structure, whether to use `format="json"` or a
JSON-schema `format` dict, and whether `generate` or `chat` fits better.
`temperature=0.0` is strongly recommended for reproducibility.

## Completion criteria

From the module root:

```bash
uv run python 15-llm-in-pipelines/03-classification-and-enrichment/tests/validate.py
```

The validator (after confirming Ollama is reachable and both models are
pulled) calls `classify_record` once per record in
`data/classification.json`, live, and checks:

- **Category macro-F1** (primary) -- unweighted mean of per-category F1
  across the 8-label closed set, at or above a threshold calibrated
  against a live 7B-model run with headroom. A predicted category is
  normalized (stripped, lowercased) before comparison; anything that
  doesn't map onto one of the 8 known labels counts as wrong.
- **Brand accuracy** (secondary) -- fraction of records where the
  extracted brand matches gold under loose text normalization, at or above
  its own (lower) threshold.

Prints `PASSED` with both measured numbers, or `NOT PASSED: <reason>` and
exits 1 -- including while `src/classify.py` is still unimplemented
(`NotImplementedError` surfaces as a clean message, no traceback).

## Estimated evenings

2

## Topics to read up on

- Zero-shot and few-shot classification with instruction-tuned LLMs
- Closed-set label prompting -- why an LLM needs the exact label vocabulary
  spelled out, not just a general task description
- JSON/structured output modes for local LLM servers, and defensive
  parsing of model responses that don't quite conform
- Macro-averaged F1 vs. accuracy on an imbalanced label set, and why a
  constant/majority-class prediction scores near zero on macro-F1 even
  when its accuracy looks deceptively decent
- Prompt engineering for disambiguation: giving a model short category
  definitions or boundary examples to resolve genuinely ambiguous items

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API
contract, the exact dataset generation process (including how the
diluted-signal titles are constructed), and this task's verification
margins -- spoilers. Don't read it before finishing this task.
