"""Validator for 15-llm-in-pipelines task 01 -- swappable-llm-client.

This task is graded almost entirely DETERMINISTICALLY, by injecting fake
`harness.llm.LLMClient` subclasses into the learner's `ResilientClient`
and asserting on its return value and `.stats` counters -- never on a live
model's content. Five fakes exercise the five documented paths:

  1. transient-error-then-valid  -> retry recovers within `max_retries`.
  2. junk-then-valid JSON        -> reask recovers within `max_reasks`.
  3. always invalid JSON         -> reask budget exhausted, StructuredOutputError.
  4. always raises, good fallback-> primary exhausts retries, fallback used.
  5. both always raise           -> fallback also fails outright, call raises.

Exactly ONE live call closes out the validator: `require_client()` gates
it (so an unreachable Ollama reports as infra-not-ready, not a confusing
failure), wraps the real client in a `ResilientClient`, and does a single
trivial `structured()` extraction against `qwen2.5:7b-instruct`.

Run from the module root:

    uv run python 01-swappable-llm-client/tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import guarded, not_passed, passed, require_client  # noqa: E402
from harness.llm import LLMClient  # noqa: E402
from src.client import ResilientClient, StructuredOutputError, TransientError  # noqa: E402

SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "in_stock": {"type": "boolean"}},
    "required": ["name", "in_stock"],
}


class FakeClient(LLMClient):
    """Minimal `LLMClient` -- no network calls. `responses` is a list of
    items, each either a JSON string to return from `generate()` or an
    Exception INSTANCE to raise. Calls beyond `len(responses)` clamp to
    the last entry (so "always raises" / "always invalid" needs only one
    list entry)."""

    def __init__(self, responses, model="fake-model", embed_model="fake-embed"):
        self._responses = list(responses)
        self.calls = 0
        self._model = model
        self._embed_model = embed_model

    def _next(self):
        idx = min(self.calls, len(self._responses) - 1)
        item = self._responses[idx]
        self.calls += 1
        if isinstance(item, BaseException):
            raise item
        return item

    def generate(self, prompt, *, system=None, format=None, temperature=0.0, options=None):
        return self._next()

    def chat(self, messages, *, format=None, temperature=0.0):
        return self._next()

    def embed(self, texts):
        return [[0.0] for _ in texts]

    @property
    def model(self):
        return self._model

    @property
    def embed_model(self):
        return self._embed_model


def check_retry_recovers():
    primary = FakeClient([TransientError("boom"), TransientError("boom"), '{"name": "Widget", "in_stock": true}'])
    rc = ResilientClient(primary, max_retries=2, max_reasks=1, backoff_base=0.0)
    result = rc.structured("extract", schema=SCHEMA)
    if result != {"name": "Widget", "in_stock": True}:
        return False, f"retry-recovery: expected the valid parsed dict, got {result!r}"
    if primary.calls != 3:
        return False, f"retry-recovery: expected 3 primary generate() calls (2 failures + 1 success), got {primary.calls}"
    stats = rc.stats
    if stats["retries"] != 2:
        return False, f"retry-recovery: expected stats['retries']==2, got {stats['retries']}"
    if stats["reasks"] != 0:
        return False, f"retry-recovery: expected stats['reasks']==0 (no invalid output involved), got {stats['reasks']}"
    if stats["fallbacks"] != 0:
        return False, f"retry-recovery: expected stats['fallbacks']==0 (no fallback configured), got {stats['fallbacks']}"
    if stats["calls"] != 3:
        return False, f"retry-recovery: expected stats['calls']==3, got {stats['calls']}"
    return True, ""


def check_reask_recovers():
    primary = FakeClient(["not valid json at all", '{"name": "Widget"}', '{"name": "Widget", "in_stock": true}'])
    rc = ResilientClient(primary, max_retries=0, max_reasks=2, backoff_base=0.0)
    result = rc.structured("extract", schema=SCHEMA)
    if result != {"name": "Widget", "in_stock": True}:
        return False, f"reask-recovery: expected the valid parsed dict, got {result!r}"
    if primary.calls != 3:
        return False, f"reask-recovery: expected 3 primary generate() calls (unparseable, missing field, valid), got {primary.calls}"
    stats = rc.stats
    if stats["reasks"] != 2:
        return False, f"reask-recovery: expected stats['reasks']==2, got {stats['reasks']}"
    if stats["retries"] != 0:
        return False, f"reask-recovery: expected stats['retries']==0 (no transient errors involved), got {stats['retries']}"
    return True, ""


def check_reask_budget_exhausted():
    primary = FakeClient(["still not json"])
    rc = ResilientClient(primary, max_retries=0, max_reasks=1, backoff_base=0.0)
    try:
        rc.structured("extract", schema=SCHEMA)
    except StructuredOutputError:
        pass
    except Exception as e:
        return False, f"reask-exhaustion: expected StructuredOutputError, got {type(e).__name__}: {e}"
    else:
        return False, "reask-exhaustion: expected StructuredOutputError to be raised, but structured() returned normally"
    if primary.calls != 2:
        return False, f"reask-exhaustion: expected 2 primary generate() calls (1 ask + 1 reask), got {primary.calls}"
    if rc.stats["reasks"] != 1:
        return False, f"reask-exhaustion: expected stats['reasks']==1, got {rc.stats['reasks']}"
    return True, ""


def check_fallback_used():
    primary = FakeClient([TransientError("down")])
    fallback = FakeClient(['{"name": "Widget", "in_stock": true}'])
    rc = ResilientClient(primary, fallback, max_retries=1, max_reasks=0, backoff_base=0.0)
    result = rc.structured("extract", schema=SCHEMA)
    if result != {"name": "Widget", "in_stock": True}:
        return False, f"fallback-used: expected the fallback's valid parsed dict, got {result!r}"
    if primary.calls != 2:
        return False, f"fallback-used: expected 2 primary generate() calls (1 attempt + 1 retry, both failing), got {primary.calls}"
    if fallback.calls != 1:
        return False, f"fallback-used: expected 1 fallback generate() call, got {fallback.calls}"
    stats = rc.stats
    if stats["fallbacks"] != 1:
        return False, f"fallback-used: expected stats['fallbacks']==1, got {stats['fallbacks']}"
    if stats["retries"] != 1:
        return False, f"fallback-used: expected stats['retries']==1 (primary's one retry), got {stats['retries']}"
    if stats["calls"] != 3:
        return False, f"fallback-used: expected stats['calls']==3 (2 primary + 1 fallback), got {stats['calls']}"
    return True, ""


def check_both_fail():
    primary = FakeClient([TransientError("down")])
    fallback = FakeClient([TransientError("also down")])
    rc = ResilientClient(primary, fallback, max_retries=0, max_reasks=0, backoff_base=0.0)
    try:
        rc.structured("extract", schema=SCHEMA)
    except Exception:
        pass
    else:
        return False, "both-fail: expected an exception to propagate when both primary and fallback fail outright"
    if primary.calls != 1 or fallback.calls != 1:
        return False, f"both-fail: expected 1 call each to primary and fallback, got primary={primary.calls}, fallback={fallback.calls}"
    if rc.stats["fallbacks"] != 1:
        return False, f"both-fail: expected stats['fallbacks']==1 (fallback was still attempted), got {rc.stats['fallbacks']}"
    return True, ""


def check_live_smoke():
    client = require_client()
    rc = ResilientClient(client, max_retries=2, max_reasks=2, backoff_base=0.5)
    result = rc.structured(
        "Extract product info from this listing: 'Wireless Mouse - In Stock, $19.99'. "
        "Respond with ONLY a JSON object with exactly these two keys: "
        '"name" (string, the product name) and "in_stock" (boolean, true or false). '
        "No other keys, no markdown, no explanation.",
        schema=SCHEMA,
    )
    if not isinstance(result, dict):
        return False, f"live-smoke: structured() must return a dict, got {type(result).__name__}"
    if "name" not in result or "in_stock" not in result:
        return False, f"live-smoke: expected keys 'name' and 'in_stock' in the result, got {sorted(result.keys())}"
    if not isinstance(result["in_stock"], bool):
        return False, f"live-smoke: expected result['in_stock'] to be a bool, got {type(result['in_stock']).__name__}: {result['in_stock']!r}"
    if rc.stats["calls"] < 1:
        return False, f"live-smoke: expected stats['calls']>=1 after a live call, got {rc.stats['calls']}"
    return True, ""


@guarded
def main():
    checks = [
        ("retry-with-backoff recovers within budget", check_retry_recovers),
        ("reask recovers within budget", check_reask_recovers),
        ("reask budget exhaustion raises StructuredOutputError", check_reask_budget_exhausted),
        ("primary exhaustion falls back", check_fallback_used),
        ("fallback also failing outright raises", check_both_fail),
    ]
    for label, check in checks:
        ok, msg = check()
        if not ok:
            not_passed(f"[{label}] {msg}")

    ok, msg = check_live_smoke()
    if not ok:
        not_passed(f"[live smoke] {msg}")

    passed("all deterministic paths (retry, reask, fallback, exhaustion) plus one live smoke call verified")


if __name__ == "__main__":
    main()
