"""t01 -- swappable-llm-client: a resilience wrapper around harness.llm.LLMClient.

This module does NOT reimplement an LLM transport. Every actual network
call still goes through a `harness.llm.LLMClient` (Ollama or OpenAI, or a
test fake that subclasses it) -- `ResilientClient` below only wraps ONE
(or two, primary + fallback) of those with three independent policies a
production pipeline needs and a raw provider client doesn't give you:

  - retry-with-backoff on transient (network/provider) failures,
  - reask-on-invalid-output for JSON extraction, bounded by a budget,
  - primary-to-fallback provider swap when the primary fails outright,

plus cumulative call accounting (`.stats`) so a pipeline operator can tell,
after a batch run, how much of that resilience machinery actually fired.

`TransientError` and `StructuredOutputError` below are given, fully
implemented -- plain marker exception types, not part of the exercise.
`ResilientClient` is the scaffold to implement; every method's docstring
spells out the exact contract the validator depends on.
"""

from __future__ import annotations


class TransientError(Exception):
    """Marker exception for a transient, retryable failure from an
    LLMClient (a timeout, a connection reset, a 5xx from the provider).

    `ResilientClient`'s retry loop retries ONLY `TransientError` (and
    subclasses of it) raised by the wrapped client's `generate()`. Any
    other exception type is treated as non-retryable -- it propagates
    immediately and counts as that client failing outright, the same as
    exhausting the retry budget would.

    The fakes in `tests/validate.py` raise this directly to simulate a
    flaky provider; a real provider integration would be responsible for
    translating its own transport-level failures (e.g.
    `httpx.TransportError`, a 5xx `httpx.HTTPStatusError`) into this type
    before -- or as part of -- calling into a `ResilientClient`. That
    translation is out of scope for this task, which is graded entirely
    against injected fakes that raise `TransientError` directly.
    """


class StructuredOutputError(Exception):
    """Raised by `ResilientClient.structured()` when the client being
    tried (primary, or fallback if the primary failed outright and a
    fallback was configured) exhausts its reask budget without ever
    producing a response that both parses as JSON and passes the caller's
    `schema` check."""


class ResilientClient:
    """Resilience wrapper around any `harness.llm.LLMClient`.

    Wraps a PRIMARY client (and an optional FALLBACK client) with three
    independent policies -- retry-with-backoff on transient failures,
    reask-on-invalid-output for structured JSON extraction, and a
    primary-to-fallback provider swap -- plus cumulative call accounting
    exposed via `.stats`.

    Args:
        primary: the `LLMClient` to try first.
        fallback: an optional second `LLMClient`, tried only after
            `primary` fails outright (see `structured` below for exactly
            what "fails outright" means). `None` means no fallback -- a
            primary failure raises directly out of `structured()`.
        max_retries: how many additional attempts (beyond the first) a
            SINGLE `generate()` call gets when it raises `TransientError`
            (or a subclass), before that call is considered failed.
            `max_retries=0` means no retries -- one attempt only.
        max_reasks: how many additional prompts (beyond the first) get
            sent to a client when its response fails to parse as JSON or
            fails the `schema` check, before that client is considered to
            have exhausted its reask budget. `max_reasks=0` means no
            reasks -- one ask only.
        backoff_base: seconds. The Nth retry (0-indexed) of a given
            `generate()` call sleeps `backoff_base * (2 ** N)` seconds
            before trying again, so backoff strictly increases with each
            retry. `backoff_base=0` disables sleeping entirely -- set this
            in tests so retry paths run instantly.

    `max_retries` and `max_reasks` are required keyword arguments (no
    default) -- every caller must make an explicit choice. `backoff_base`
    defaults to `0.1`.
    """

    def __init__(self, primary, fallback=None, *, max_retries, max_reasks, backoff_base=0.1):
        raise NotImplementedError

    def structured(self, prompt, *, schema, system=None) -> dict:
        """Get a JSON object out of the wrapped client(s), retrying on
        transient failure, reasking on invalid output, and falling back to
        `self.fallback` if `self.primary` fails outright.

        Args:
            prompt: the user prompt.
            schema: dict | callable -- how a parsed JSON response is
                checked before being accepted:

                - dict: a minimal JSON-Schema-like object,
                  `{"type": "object"?, "properties": {field: {"type":
                  jsontype}, ...}?, "required": [field, ...]?}`. Validation,
                  in order: (1) the parsed value must be a `dict` -- else
                  invalid ("expected a JSON object"); (2) every name in
                  `required` must be a key of the parsed dict -- else
                  invalid ("missing required field: <name>"); (3) for
                  every name that is BOTH a key of `properties` AND a key
                  of the parsed dict, the parsed value's Python type must
                  match the declared `jsontype`: `"string"` -> `str`,
                  `"number"` -> `int` or `float` (but not `bool`, even
                  though `bool` is technically an `int` subclass -- a JSON
                  boolean must never satisfy a "number" check),
                  `"integer"` -> `int` only (`bool` and `float` excluded),
                  `"boolean"` -> `bool`, `"array"` -> `list`, `"object"`
                  -> `dict`. A mismatch is invalid ("field <name>:
                  expected <jsontype>, got <actual type name>"). Keys
                  present in the parsed dict but absent from `properties`
                  are ignored, not an error.
                - callable: called as `schema(parsed)`, where `parsed` is
                  whatever `json.loads` produced (not guaranteed to be a
                  dict before the callable runs). Must return `None` if
                  `parsed` is valid, or a non-empty `str` describing what
                  is wrong if it isn't. Any exception raised by the
                  callable itself is treated the same as a returned error
                  string -- caught, with `str(exception)` used as the
                  validation-error text -- and must NOT propagate out of
                  `structured()`.

                Either form's error text becomes the reask signal: on a
                reask, append a suffix to the ORIGINAL `prompt` that
                includes the error text and asks for corrected, valid
                JSON only. Exact wording is your choice -- the fakes in
                `tests/validate.py` don't parse prompt content, only how
                many times a client was called and with what
                response/exception sequence. Each reask prompt is
                `prompt` plus ONE error suffix describing the immediately
                preceding failure -- not an accumulating chain of every
                prior attempt's error.
            system: optional system prompt, passed straight through to
                `generate(..., system=system, ...)`.

        Returns:
            dict: the parsed, schema-valid JSON object.

        Raises:
            StructuredOutputError: the client being tried (primary, or
                fallback if one is configured and primary failed outright)
                exhausted its reask budget without ever producing valid
                output.
            Exception: whatever the underlying client(s) raised -- a
                `generate()` call failed with something other than
                `TransientError`, or kept raising `TransientError` until
                `max_retries` was exhausted and there was no fallback (or
                the fallback also failed outright).

        Algorithm, per client (`primary` first, then `fallback` only if
        `primary` fails outright and `fallback` is not `None`):

          1. Attempt up to `max_reasks + 1` total "asks" against this
             client. Ask 0 uses `prompt` as given; ask K (K >= 1) uses
             `prompt` plus a suffix describing why ask K-1's output was
             rejected (see the `schema` paragraph above).
          2. Each ask calls `client.generate(current_prompt, system=system,
             format="json", temperature=0.0)`, retried up to `max_retries`
             additional times (sleeping `backoff_base * 2**N` between the
             Nth and (N+1)th attempt) whenever the call raises
             `TransientError`. Any OTHER exception type is not retried --
             it propagates immediately and counts as this client failing
             outright, same as exhausting the retry budget. If every
             attempt for this ask raises `TransientError` and the retry
             budget is exhausted, this client has failed outright -- stop
             asking it (do not spend any remaining reask budget) and go to
             step 4.
          3. If a response comes back: try `json.loads` on it, then, if it
             parsed, validate it against `schema`. If both succeed, return
             the parsed dict immediately -- this client succeeded, the
             fallback (if any) is never consulted. If either step fails
             and reask budget remains, go to the next ask (step 1) with
             that failure's error text appended. If either step fails and
             the reask budget is exhausted, this client has failed
             outright -- if there is no fallback to try, raise
             `StructuredOutputError`; otherwise go to step 4.
          4. This client (primary) failed outright, via step 2 or step 3.
             If `self.fallback` is not `None`: record one fallback in
             `stats`, then repeat steps 1-3 against `self.fallback`,
             restarting from the ORIGINAL `prompt` (not primary's failed
             final prompt). Whatever that fallback attempt returns or
             raises (including `StructuredOutputError` if the fallback
             also exhausts its own reask budget) is the final outcome of
             this `structured()` call. If `self.fallback` is `None`, or
             this failure just happened on the FALLBACK attempt itself,
             re-raise whatever exception step 2/3 produced instead.

        Every underlying `generate()` call made anywhere in this
        algorithm -- successful or not, primary or fallback, first ask or
        a reask -- increments `stats["calls"]` by 1 and adds its
        wall-clock duration to `stats["total_latency"]`. A successful call
        additionally adds an approximate token count (see `stats` below)
        to `stats["total_tokens"]`. Each retry attempt (a call beyond the
        first for a given ask) increments `stats["retries"]` by 1. Each
        reask (an ask beyond the first for a given client) increments
        `stats["reasks"]` by 1. `stats["fallbacks"]` is incremented by
        exactly 1 per `structured()` call that reaches step 4 with a
        non-`None` fallback (never more than 1 per call, since there is
        only one fallback client). Stats accumulate across every call to
        `structured()` made on this instance -- they are never reset.
        """
        raise NotImplementedError

    @property
    def stats(self) -> dict:
        """Cumulative call accounting since this `ResilientClient` was
        constructed, across every `structured()` call made on it. A dict
        with exactly these keys:

          calls:         int, total `generate()` invocations attempted
                         (primary + fallback, every retry and every
                         reask), successful or not.
          retries:       int, total retry attempts due to `TransientError`
                         (calls beyond the first attempt of each ask).
          reasks:        int, total reask attempts due to invalid or
                         unparseable output (asks beyond the first ask of
                         each client attempt).
          fallbacks:     int, total number of `structured()` calls that
                         had to switch from `primary` to `fallback`.
          total_latency: float, cumulative wall-clock seconds spent inside
                         `generate()` calls (successful and failed).
          total_tokens:  int, approximate token count across successful
                         calls only. `LLMClient` exposes no real
                         usage/token-count API, so use a whitespace-token
                         proxy: for each successful call, add
                         `len(prompt.split()) + len(response.split())`
                         (the prompt actually sent for that call, i.e.
                         including any reask suffix, and the raw response
                         text returned).

        Returns a plain `dict`, freshly built on each access (a snapshot,
        not a live reference to internal mutable state) -- mutating the
        returned dict must not affect subsequent reads of `stats`.
        """
        raise NotImplementedError
