# Module 15 design — SPOILERS, learner off-limits

Do not read this before attempting the module's tasks. It documents the
shared harness API every task and validator depends on, the dataset schema
and generator draw order, the committed ground-truth values, and the
verification philosophy per task type.

This file is the shared contract for every agent working on this module
(infra, generator, task authors, validators). If you change something here,
regenerate and reverify and update every consumer in the same change.

## Purpose

Use a local Ollama-served 7B model (`qwen2.5:7b-instruct` for chat/JSON
extraction, `nomic-embed-text` for embeddings) as a PIPELINE COMPONENT, not
a chat toy: structured extraction from messy HTML, record classification +
enrichment, embedding-based dedup, and a mini-RAG lookup over the sandbox's
own docs. The LLM client (`harness/llm.py`) is built so a cloud API (OpenAI)
can replace Ollama with a single `LLM_PROVIDER=openai` env change — nothing
in a task's `src/` should import a provider-specific SDK.

## Docker stack (`docker-compose.yml`)

One service, `ollama` (image `ollama/ollama:latest`), host port
`${SANDBOX_15_OLLAMA_PORT:-11439}:11434`, a named volume
`ollama-models:/root/.ollama`, GPU reservation via compose
`deploy.resources.reservations.devices` (nvidia, `count: all`,
`capabilities: [gpu]`). Healthcheck runs `ollama list` (the image ships no
curl/wget, and `ollama list` is the CLI's own client for `GET /api/tags`, so
it exercises the same readiness signal the spec asked for).

The compose file does NOT auto-pull models. After `docker compose up -d`,
the learner must run once:

```
docker compose exec ollama ollama pull qwen2.5:7b-instruct
docker compose exec ollama ollama pull nomic-embed-text
```

`CONVENTIONS.md`'s ports table gained one row:
`15-llm-in-pipelines | Ollama (HTTP API) | 11439 | SANDBOX_15_OLLAMA_PORT`.

This session's verification ran against an already-running out-of-band
Ollama container (`s15-ollama-test`, same port 11439) rather than starting
a second one from this compose file — starting a second container would
have collided on the port. `docker compose config` was used to validate the
YAML instead of `docker compose up`.

## `pyproject.toml`

`name = "llm-in-pipelines"`, `requires-python = ">=3.12,<3.14"`. Dependencies:
`httpx>=0.27`, `numpy>=1.26`, `pytest>=8`. Deliberately no `ollama` or
`openai` SDK dependency — both providers in `harness/llm.py` are raw `httpx`
calls, which is the point of the swappable-client lesson. `uv sync` verified
clean; `uv.lock` committed.

## Harness API

### `harness/llm.py` — provided transport (tasks 02-06 import and use as-is)

Zero import-time side effects: no client constructed, no network call, until
`get_client()` or a provider class is explicitly instantiated.

```python
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11439"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "qwen2.5:7b-instruct"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_TIMEOUT = 120.0

class LLMClient(ABC):
    def generate(self, prompt, *, system=None, format=None, temperature=0.0, options=None) -> str
    def chat(self, messages, *, format=None, temperature=0.0) -> str
    def embed(self, texts: list[str]) -> list[list[float]]      # batched; loops per-text for Ollama
    @property model -> str
    @property embed_model -> str

class OllamaClient(LLMClient):   # httpx to {base}/api/generate, /api/chat, /api/embeddings
class OpenAIClient(LLMClient):   # httpx to {base}/chat/completions, {base}/embeddings

def get_client() -> LLMClient    # factory from LLM_PROVIDER env (default "ollama")
def cosine(a, b) -> float        # numpy cosine similarity, handles zero-norm -> 0.0
```

Env config (all read inside `__init__`, not at import time):
`LLM_PROVIDER` (`ollama`|`openai`, default `ollama`), `LLM_MODEL`,
`LLM_EMBED_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY` (openai only), `LLM_TIMEOUT`.

`format` on `generate`/`chat`: `None` (free text), `"json"` (provider JSON
mode — Ollama's `format: "json"`, OpenAI's `response_format:
{"type":"json_object"}`), or a JSON-schema dict (Ollama passes it straight
through as `format`; OpenAI maps it to a `json_schema` structured-output
`response_format`).

Task 01 (`swappable-llm-client`) is the one task that reaches past this
file: it builds a resilience wrapper (reask-on-invalid-JSON, retry with
backoff, primary→fallback provider swap, token/latency accounting) in its
own `src/`, tested with injected fake `LLMClient` implementations for the
deterministic paths plus one live smoke call. Tasks 02-06 use
`get_client()` directly (or the learner's own thin usage of it) with no
retry/fallback expectations baked into the base transport itself — that
resilience is task 01's deliverable, not part of the provided harness.

### `harness/common.py` — validator/generator plumbing

Identical `not_passed`/`passed`/`guarded`/`_last_line`/`write_baseline`/
`read_baseline`/`load_ground_truth` plumbing to modules 10/11/14 (verbatim
semantics — NOT PASSED + exit 1 on failure, PASSED + exit 0 on success,
`guarded` catches unexpected exceptions and `NotImplementedError`,
`SystemExit` passes through). No `load_observations` equivalent (module 15
has 5 distinct data shapes, not one shared frame) — task validators load
`data/extraction.json` etc. directly or call the `generate.py` builders.

```python
MODULE_ROOT, DATA_DIR, GROUND_TRUTH_PATH, CORPUS_DIR   # Paths

def require_client() -> LLMClient
    # Probes GET {LLM_BASE_URL}/api/tags for the ollama provider, checks
    # both LLM_MODEL and LLM_EMBED_MODEL are present in the tag list.
    # NOT PASSED with an actionable "docker compose up -d, then pull ..."
    # message on any failure (connection refused, missing model). For the
    # openai provider, checks LLM_API_KEY is set (first live call surfaces
    # auth/network errors on its own). Returns get_client() on success.
    # This is the load-bearing distinction between "infra not ready" and
    # "learner's solution is wrong" -- every LLM-dependent validator must
    # call this before trusting any LLM-derived output.

def prf_from_sets(pred: set, gold: set) -> (precision, recall, f1)
def accuracy(preds: list, golds: list) -> float
def macro_f1(preds: list, golds: list, labels: list) -> float
    # unweighted mean of per-label one-vs-rest F1, sklearn-macro semantics;
    # a label absent from both preds and golds contributes F1=1.0
def pair_f1(pred_labels: list, gold_labels: list) -> (precision, recall, f1)
    # clustering pairwise F1 over all C(n,2) item pairs: does the pair fall
    # in the same cluster under pred vs under gold
def norm_price(s) -> float | None
    # handles: $/€/£ prefix or USD/EUR/GBP suffix, comma-thousands
    # ("1,299.00"), dot-thousands + comma-decimal European style
    # ("1.299,00"), bare 2-digit decimal comma ("19,99"), stray whitespace;
    # returns None for empty/unparseable input ("N/A", "call for price")
def norm_text(s) -> str
    # lowercase, strip punctuation, collapse whitespace -- loose string match
```

All third-party imports (`httpx`, `numpy`) inside `common.py` are lazy
(imported inside the function that needs them) except the stdlib
`json`/`sys`/`pathlib` at module top — importing `harness.common` has zero
side effects, matching module 14's discipline.

## `generate.py` — SEED = 151515, draws

Every `build_*` function is PURE (numpy + stdlib only, no file I/O).
`build_catalog(seed, scale)` is the only one that takes `scale`; the other
four always draw from a fixed **`build_catalog(seed, 1.0)`** regardless of
the module's `SCALE` env — they are LLM-call-bound eval sets (every item
costs a live model call to grade in a validator), so their size is fixed
rather than scaling with `SCALE`. Only the catalog's own size scales
(`n = round(120 * scale)`).

Each builder opens its own `np.random.default_rng(seed)` — all five reuse
the same `SEED` value but as independent streams (no shared rng object
across builders), which is safe since each function's draws are logically
separate.

### `build_catalog(seed, scale) -> list[dict]`

`{product_id, name, brand, category, price(float), currency("USD" always —
canonical/clean by construction), specs(dict), in_stock(bool)}`. `n = round(120
* scale)`, category assignment is a deterministic round-robin over
`CATEGORIES` (`np.arange(n) % 8`, no rng draw) rather than Zipf — a small
catalog needs even category coverage for classification/dedup sampling
to work, not a popularity skew.

`CATEGORIES` reuses module 14's exact 8-category list (electronics,
home-goods, kitchen, toys, sporting-goods, apparel, books, garden) per the
task spec's explicit instruction — same names, but module 15's own
`CATEGORY_PRICE_PROFILE` / `CATEGORY_TOKENS` (brands, nouns) are a fresh,
independent vocabulary, not imported from module 14.

Draw order (fixed): C1 category (no draw) → C2 `brand_idx, adj_idx,
noun_idx, model_num, model_letter_idx` → C3 price z-score (log-normal per
category, `CATEGORY_PRICE_PROFILE`) → C4 `color_idx, material_idx,
weight_kg, warranty_years` → C5 `in_stock` (`P(True)=0.85`).

Every noun token in `CATEGORY_TOKENS` is hyphenated/single-word by
construction (e.g. `cutting-board`, `action-figure`) so `name.split()`
always yields exactly `[brand, adj, noun, model]` — load-bearing for the
dedup builder's distortion functions, which index into that split.

### `build_extraction_set(seed) -> list[dict]`

50 items, `{snippet_id, html, gold: {name, brand, price, currency,
in_stock}}`. Draws 50 distinct products (no replacement) from the
scale-1.0 catalog, assigns one of 6 hostile HTML templates and one of 3
currencies (`USD` 0.7 / `EUR` 0.2 / `GBP` 0.1) per snippet:

1. `_tmpl_nested_divs` — plain but nested tag structure, price in a
   generically-named `<span class="amt">`.
2. `_tmpl_prose` — price stated in a marketing sentence ("Now only $X --
   In stock."), no dedicated price element at all.
3. `_tmpl_attributes` — every field lives in a `data-*` attribute
   (`data-price`, `data-currency`, `data-in-stock="true"/"false"` as a
   lowercase string), visible text repeats only the name.
4. `_tmpl_entity_noise` — `&nbsp;` entities, irregular newlines/indentation
   around otherwise-normal tags.
5. `_tmpl_broken_tags` — unclosed `<b>`/`<p>`/`<li>`, no closing `</ul>`
   balance — the kind of malformed markup a strict CSS-selector walk chokes
   on but a tolerant parser or an LLM reading raw text does not.
6. `_tmpl_cents_implied_stock` — price as integer cents in
   `data-price-cents` (no decimal point anywhere), stock only implied by
   the presence/absence of an "Add to Cart" button vs. an "unavailable"
   span, never a boolean field.

`gold.price` is always the canonical float (e.g. `19.99`), never the raw
on-page string — the validator compares the learner's parsed number, not a
string match. `gold.currency` matches whatever currency the snippet was
rendered in (not necessarily USD). `gold.in_stock` is the underlying
product's `in_stock`, which every template renders a signal for (never
truly silent) — the hostility is in the surface form and placement, not in
withholding the fact.

### `build_classification_set(seed) -> list[dict]`

80 items, `{record_id, title, description, gold_category, gold_brand}`.
Draws 80 distinct products from the catalog and REGENERATES a title (not
the catalog's own `name`) using the same generic-brand-pool +
cross-category-noun-noise dilution mechanism as module 14's title
construction: `GENERIC_BRAND_FRAC=0.30` chance the brand token is drawn
from a shared, category-agnostic `GENERIC_BRANDS` pool instead of the
product's own category brand list; `CROSS_NOUN_NOISE_FRAC=0.25` chance the
noun token is borrowed from a different category's noun list
(`cross_offset` guarantees a genuinely different category). `description`
is a short, mostly category-neutral marketing sentence from an 8-template
pool, with a further 0.3 chance of appending an off-topic
`"Popular among {other-category-activity} fans this season."` clause —
another deliberate false signal.

**`gold_brand` is the brand token actually embedded in the generated title**
(generic or category-specific, whichever was rolled) — an extractable
field, distinct from `gold_category`, which is the hard part precisely
because the title/description signal is diluted. Do not confuse
`gold_brand` with the underlying catalog product's true brand; they may
differ when the generic-brand roll fires.

### `build_dedup_set(seed) -> list[dict]`

~20 clusters (`N_DEDUP_CLUSTERS=20`, exactly 20 distinct products picked
without replacement), 1-4 title variants per cluster
(`DEDUP_VARIANT_COUNTS=[1,2,3,4]`, `weights=[0.15,0.35,0.35,0.15]`) →
**55 items this session** (varies run-to-run only if the weights/seed
change — fixed and reproducible at `SEED=151515`). Variant 0 of every
cluster is always the untouched catalog `name` (so at least one item per
cluster is a byte-exact anchor); later variants each apply exactly one of 4
distortions, chosen per-variant: `_distort_abbreviation` (adjective token
via a fixed `ABBR_MAP`, or first-4-chars+`.` fallback),
`_distort_reorder` (`{adj} {noun} {model} {brand}`),
`_distort_punctuation` (`{brand}, {adj} {noun} - {model}`),
`_distort_brand_swap` (`{adj} {noun} {model} ({brand})`). Final item list
order is shuffled (`rng.permutation`) so items are never grouped by
cluster — a validator/learner cannot cheat by assuming adjacency.

### `build_rag_corpus(seed) -> (docs, qa)`

**Deviation from a "scrape it live" design, deliberate**: the 6 handbook
docs and 15 QA pairs are FIXED, hand-written Python string literals — no
rng draw at all (`seed` param kept only for signature symmetry with the
other four builders). They describe THIS sandbox's own conventions (ports,
hints, verification contract, data generation rules, Python tooling,
capstone checkpoint structure) but are synthesized prose, not copied
verbatim from `CONVENTIONS.md` or any other live file. This is intentional:
pointing RAG at the live repo would make the QA gold answers drift every
time `CONVENTIONS.md` changes, breaking a previously-passing task through
no fault of the learner. The handbook is a frozen snapshot in spirit only.

Docs: `doc_id ∈ {ports-policy, hint-ladder, verification-contract,
data-generation-rules, python-tooling, capstone-checkpoints}`, each
`{doc_id, title, path: "corpus/{doc_id}.md", text}` (text is the full
markdown including its own `# Title` heading). QA: 15 pairs (3+2+3+2+2+3
across the 6 docs), each `{question, gold_doc_id, gold_answer_substring,
gold_keywords}`. `generate()` calls `_verify_rag_gold(docs, qa)` on every
run, which asserts every `gold_answer_substring` literally appears in its
`gold_doc_id`'s text — this raises (fails generation) rather than silently
shipping a broken QA pair; it caught one seeded typo mismatch during this
session's authoring (`"exit with status code 0"` vs. the doc's actual
`"exits with status code 0"`), fixed before the first successful run.

## Task-facing data files vs. gold reconstruction

`main()` writes the gold-STRIPPED versions of the derived sets to disk —
`data/extraction.json` (no `gold` key), `data/classification.json` (no
`gold_category`/`gold_brand`), `data/dedup.json` (no `gold_cluster_id`) —
plus the full corpus markdown files (`data/corpus/*.md`, which are source
material, not gold, so nothing is stripped there). This mirrors module 14's
`build_observations()` → `(df, labels)` split: the on-disk artifact never
carries the answer key. **Validators never read gold from these files** —
they call the `build_*` functions directly (`from generate import
build_extraction_set, ...`) with the same `SEED`, and pull `gold`/
`gold_category`/`gold_cluster_id` straight out of the freshly-rebuilt
in-memory objects, keyed by `snippet_id`/`record_id`/`item_id` to match
against whatever order the learner's code processed the on-disk (stripped)
file in.

`build_catalog` itself is never written to disk at all — it is pure
infrastructure other builders draw from, and the source-of-truth answer
key for anything that needs to check "did the learner recover the real
brand/category/price," reconstructed in-memory by validators exactly like
the derived sets.

## Committed ground truth (`data/ground-truth.json`)

Computed by `_ground_truth(...)`, verified reproducible across two
independent `uv run python generate.py` runs this session (byte-identical
`data_sha`):

```json
{
  "seed": 151515,
  "scale": 1.0,
  "categories": ["electronics","home-goods","kitchen","toys","sporting-goods","apparel","books","garden"],
  "n_catalog": 120,
  "n_extraction": 50,
  "n_classification": 80,
  "n_dedup": 55,
  "n_clusters": 20,
  "n_corpus_docs": 6,
  "n_qa": 15,
  "data_sha": "ad73e0688ccfe83753a57564cc2361bda8ebd9f056578d83fbb11ebde0645e44"
}
```

`data_sha` = sha256 of `json.dumps({catalog, extraction, classification,
dedup, corpus_docs, corpus_qa}, sort_keys=True, separators=(",",":"))` —
the FULL objects (gold included, pre-strip), so it detects drift in
anything the generator produces, not just what's written to the stripped
task-facing files. Any future change to `generate.py` that alters
`data_sha` at `SCALE=1.0` must be treated as a breaking change to every
task's answer key and every threshold tuned against this data.

## Verification philosophy

- **`require_client()` gates every LLM-dependent validator first.** A
  validator must never let an Ollama connection error surface as a
  confusing metric failure ("precision 0.0") — it must be unambiguous that
  the infra isn't up, with the exact `docker compose` commands to fix it.
- **Metric thresholds are tuned for a 7B model's sampling variance**, not
  for a frontier model. Task authors calibrating thresholds against
  `qwen2.5:7b-instruct` at `temperature=0` should expect real but imperfect
  performance and set thresholds with generous headroom — a threshold that
  only a near-perfect run clears will be flaky across machines/driver
  versions even at temperature 0, because llama.cpp's batching and CUDA
  nondeterminism mean output is not bit-identical run-to-run despite
  greedy decoding.
- **`temperature=0` everywhere** a validator makes a live call, to minimize
  (not eliminate — see above) run-to-run variance.
- **Validators compute gold independently and never trust learner output as
  an oracle.** Every gold value comes from calling the `build_*` functions
  directly against the committed `SEED`, never from re-reading a file the
  learner's own code could have touched.
- **A constant/degenerate baseline must FAIL each metric threshold.** For
  task 03 (classification), predicting the majority category for every
  record must not clear the macro-F1 bar (macro-F1 punishes exactly this,
  since minority-category F1 collapses to 0). For task 04 (dedup),
  "everything is its own cluster" and "everything is one cluster" must both
  fail `pair_f1`'s threshold (the former craters recall, the latter craters
  precision). Task authors must verify this empirically per task, the same
  way module 14 verified its macro-F1 ceiling wasn't trivially 1.0.
- **Structured-output validators (task 02) grade parsed values, not
  strings**: `gold.price` is a float, so a validator must parse the
  learner's extracted price (however it chose to represent it) and compare
  with a tolerance — never demand the exact on-page string. `norm_price` /
  `norm_text` in `common.py` exist for exactly this.
- **RAG (task 05) grades retrieval and answer separately**: `hit@k` (is
  `gold_doc_id` among the top-k retrieved chunks) is the robust PRIMARY
  metric, because it is deterministic given the embedding model and
  doesn't depend on the generation step's phrasing. Answer-contains-fact
  (`gold_answer_substring` or `gold_keywords` overlap) is a SECONDARY
  metric layered on top, since generation quality is the noisier signal of
  the two.
- **The capstone (task 06)** is the only task that composes multiple
  builders in one pipeline. CP1 (steady) grades against the clean
  extraction/classification/dedup sets as built. CP2 (chaos) is expected to
  feed the pipeline noisier/malformed variants (task 06's own authoring
  responsibility, out of scope for this generator) and check graceful
  degradation (quarantine routing) rather than the CP1 thresholds. CP3 is a
  `DESIGN.md` review plus a subprocess re-run of CP1 and CP2.

## Planned task list (for the next authoring wave — do not create these
directories yet; this is the alignment contract)

- **`01-swappable-llm-client`** — a pipeline-grade resilience wrapper in
  `src/` over `harness.llm`: enforced structured/JSON output with schema
  validation + bounded reask on invalid output, timeout + bounded
  retry-with-backoff on transient errors, primary→fallback provider swap on
  repeated failure, token/latency accounting. Tested with INJECTED fake
  `LLMClient` implementations (flaky-then-valid, always-junk, always-down)
  for the deterministic retry/reask/fallback paths, plus one live smoke
  call against real Ollama. Foundational "make LLMs pipeline-safe" lesson —
  every later task benefits from (but does not strictly require) reusing
  this wrapper.
- **`02-structured-extraction`** — extract `{name, brand, price, currency,
  in_stock}` from `build_extraction_set`'s 50 hostile HTML snippets;
  graded field-level precision/recall/exact-match vs. gold, thresholds
  calibrated for a 7B model.
- **`03-classification-and-enrichment`** — classify + enrich
  `build_classification_set`'s 80 records; accuracy/macro-F1 thresholds;
  constant-prediction baseline must fail macro-F1.
- **`04-embedding-dedup`** — dedup `build_dedup_set`'s ~55 title variants
  via `nomic-embed-text` + cosine threshold/clustering; `pair_f1`
  threshold; both degenerate baselines (all-singleton, all-one-cluster)
  must fail.
- **`05-mini-rag`** — chunk + embed the 6-doc handbook corpus, retrieve
  top-k, answer with citation against the 15 QA pairs; `hit@k` primary
  metric, answer-contains-fact secondary.
- **`06-capstone`** — end-to-end enrichment pipeline (extract → classify/
  enrich → embed-dedup → clean catalog) with a quality/confidence gate
  routing low-confidence records to quarantine, plus a RAG "explain this
  product" step. CP1 steady (clean inputs, hit quality thresholds vs.
  gold), CP2 chaos (messier inputs / injected malformed model outputs /
  forced provider-fallback — must degrade gracefully, quarantine, still
  converge), CP3 `DESIGN.md` + subprocess re-run of CP1/CP2.
