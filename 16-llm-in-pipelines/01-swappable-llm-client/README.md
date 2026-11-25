# 01 -- Swappable LLM Client

## Backstory

The rest of this module hands you `harness/llm.py` -- a clean, provider-
agnostic `LLMClient` with one job: send a prompt, get text back. It works
great in a notebook. Wire the same client into a batch pipeline that
processes a few hundred records overnight and it stops working great:
Ollama drops a connection under load and one `generate()` call raises. The
model, asked for JSON, occasionally answers in a sentence instead ("Sure,
here's the product info:") because nothing forces it not to. And someday
the team wants to point the whole pipeline at a hosted API instead of the
local model for a week -- ideally without touching every task's code.

None of that is `harness/llm.py`'s job to solve; it is deliberately a thin
transport, nothing more. It's the pipeline's job to wrap that transport in
something that survives contact with a real batch run: retry the call that
was probably just a blip, ask again (with feedback) when the output isn't
usable JSON, fail over to a second provider if the first one is really
down, and keep count of all of it so a pipeline operator can see, after
the run, how much of that machinery actually fired.

That wrapper is this task's deliverable. Every later task in this module
can build on it (none are required to).

## What's given

- `harness/llm.py` -- the `LLMClient` abstract interface
  (`generate`/`chat`/`embed`/`model`/`embed_model`) and `get_client()`, the
  provider factory. Fully implemented, not a stub -- read it, don't modify
  it.
- `src/client.py` -- the scaffold. `TransientError` and
  `StructuredOutputError` are given, fully implemented (plain marker
  exception types). `ResilientClient` is the class to implement: its
  docstring spells out the exact constructor signature, the `structured()`
  algorithm step by step, and the `.stats` dict shape the validator checks
  against.
- `harness/common.py`'s `require_client()` -- probes the configured
  provider and returns a ready `LLMClient`, with an actionable message if
  Ollama isn't up yet. Used for the one live call this task makes.

## What's required

Implement `ResilientClient` in `src/client.py`. It wraps a PRIMARY
`LLMClient` (and an optional FALLBACK `LLMClient`) and exposes:

- A constructor: `ResilientClient(primary, fallback=None, *, max_retries,
  max_reasks, backoff_base=0.1)`.
- `structured(prompt, *, schema, system=None) -> dict` -- calls the
  wrapped client's `generate(..., format="json")`, parses the result as
  JSON, validates it against `schema` (a JSON-Schema-like dict or a
  validator callable -- both forms are specified precisely in the
  docstring), and on unparseable or invalid output, RE-ASKS with the
  validation error appended to the prompt, up to `max_reasks` times.
  Raises `StructuredOutputError` once that budget is exhausted.
- Retry-with-backoff: a `generate()` call that raises `TransientError` is
  retried up to `max_retries` times, with strictly increasing backoff.
- Fallback: if the primary client fails outright (its retry budget or its
  reask budget runs out), `structured()` switches to `fallback` (if one
  was configured) and tries there instead -- only if the fallback also
  fails does the call raise.
- `.stats` -- a dict tracking cumulative calls, retries, reasks,
  fallbacks, total latency, and an approximate token count, accumulated
  across every `structured()` call made on the instance.

Read every docstring in `src/client.py` closely -- the exact algorithm
(what counts as a "retry" vs a "reask," when the fallback is consulted,
what each `stats` key means) is spelled out there in full, because the
validator's fakes are built to exercise that exact algorithm.

## Completion criteria

From the module root:

```bash
uv run python 01-swappable-llm-client/tests/validate.py
```

The validator constructs several fake `LLMClient` subclasses (defined in
`tests/validate.py`, not in `src/`) to exercise every path deterministically
-- a client that fails a fixed number of times before succeeding, one that
returns invalid JSON before eventually returning valid JSON, one that
never returns valid JSON, and one that never succeeds at all paired with a
working fallback -- and asserts on `ResilientClient`'s return values and
`.stats` counters. It then makes exactly ONE live call against the real
Ollama server (gated by `require_client()`, so an infra problem is
reported as "Ollama isn't up," never as a confusing wrapper failure) to
confirm the whole thing works end to end against a real model, not just
against fakes.

Prints `PASSED` or `NOT PASSED: <reason>` and exits 0/1 -- including while
`src/client.py` is still unimplemented (`NotImplementedError` surfaces as
a clean message, no traceback).

## Estimated evenings

2-3

## Topics to read up on

- Exponential backoff for retrying failed network calls, and why a fixed
  retry delay behaves badly under repeated failures
- Distinguishing transient/retryable failures from permanent ones -- why
  retrying a permanent failure (a malformed request, an auth error) just
  wastes time and calls
- Constrained / structured output from LLMs (JSON mode, JSON-Schema-guided
  generation) and why "ask nicely for JSON" alone is not reliable enough
  for a pipeline
- The reask (self-correction) pattern: feeding a validation error back
  into the next prompt, and why it needs a hard budget
- The circuit-breaker / fallback-provider pattern in resilient service
  design
- Why idempotent retries matter -- what could go wrong retrying a call
  that isn't safely repeatable (not an issue for a read-only `generate()`
  call, but worth understanding generally)

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API
contract, the full generator/dataset design for later tasks, and this
module's verification philosophy -- spoilers. Don't read it before
finishing this task.
