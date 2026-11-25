"""s13.t06 -- run an instrumented sample crawl, then serve /metrics.

This is the task's entrypoint. It must, in order:

  1. Run a SAMPLE crawl against the target (`harness.common.target_base_url()`,
     default http://localhost:8313) that touches enough real + bad-record
     product ids to move every counter/gauge declared in `src/metrics.py`
     that is supposed to move (see that module's docstring for exactly
     which ones the validator checks).
  2. Start serving `prometheus_client`'s WSGI `/metrics` endpoint on `port`
     (default 9113 -- the port `docker/prometheus/prometheus.yml`'s
     `spider` job scrapes via `host.docker.internal:9113`) and KEEP RUNNING
     until interrupted (Ctrl+C / SIGTERM), so Prometheus has something to
     scrape repeatedly, not a one-shot snapshot.

Suggested shape for the sample crawl (not the only valid one, but the one
`tests/validate.py` is written against):

  - Use TWO client identities, not one:
      * a "main" client (any id you like, e.g. a fresh `uuid4` or a fixed
        string) that ONLY ever requests real, non-honeypot product ids --
        this is the client whose fetch/quarantine/completeness numbers you
        want to trust. Give it a browser-like `User-Agent` +
        `Accept-Language` (see `harness.common.DEFAULT_USER_AGENT` /
        `DEFAULT_ACCEPT_LANGUAGE` for values that pass the target's header
        gate -- you still write your own request headers, this just tells
        you what the gate checks for) and PACE its requests; the target's
        rate limiter bans a client that bursts (see the module README for
        the exact thresholds). A few hundred sequential product ids at a
        gentle pace finishes in well under a second of real request time
        and stays nowhere near the ban threshold.
      * a SEPARATE, throwaway client used for exactly ONE deliberate
        request to a known honeypot id, purely to demonstrate
        `spider_honeypot_hits_total` / `spider_banned` moving. This client
        WILL get banned by that single request (the target bans on the
        first honeypot hit, no threshold) -- that is fine, and exactly why
        it must not be the same client id as your main crawl. Where to
        find a honeypot id: `data/ground-truth.json`'s `honeypot_ids`
        (committed, not off-limits) or `GET /robots.txt` +
        `data/target-spec.json` if you want to discover it more
        realistically.

  - For each id in the main sample (e.g. ids 1..300 -- low enough that all
    six bad-record defect types already appear in that range, per
    `data/ground-truth.json`'s `bad_records.by_defect`):
      * `GET /product/{id}` -- counts as strategy="html". You do not need
        to parse the markup-version-dependent HTML for this task (that is
        task 04's problem); fetching it and recording the latency/strategy
        is enough.
      * `GET /api/product/{id}` -- counts as strategy="api". This is JSON,
        trivial to inspect regardless of markup version, and is where you
        actually check field validity: does `price` exist and look sane
        (not "N/A", not negative)? Is `title` non-empty? Is `currency` a
        real code? Does `description` look truncated? Missing/invalid ->
        `metrics.record_quarantine(reason)` with the matching defect-type
        string. A non-2xx status or a request exception on EITHER fetch ->
        `metrics.record_error(reason)`.
      * Track, across the whole sample, what fraction of records have each
        of a handful of fields present (`price`, `title`, `currency`,
        `rating`, `shipping_info`, ...) and call
        `metrics.set_field_completeness(field, ratio)` once per field after
        the sample finishes (or update incrementally -- your choice).
      * Wrap each fetch with `time.perf_counter()` and pass the elapsed
        seconds to `metrics.record_fetch(strategy, seconds)`.

  - After the sample, issue the one deliberate honeypot request with the
    throwaway client, call `metrics.record_honeypot_hit()` and
    `metrics.set_banned(True)`.

Entrypoints this module must support:

    uv run python src/serve.py          # from this task's directory
    uv run python -m src.serve           # same, as a module

Both must end up calling `run_and_serve()` with its defaults. The
`tests/validate.py` MUST-PASS check launches this file as a real subprocess
and polls `GET http://127.0.0.1:9113/metrics` until it responds -- so
`run_and_serve` needs to finish the sample crawl and start serving within a
reasonable time (keep the sample small; see above).
"""

import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    DEFAULT_ACCEPT_LANGUAGE,
    DEFAULT_USER_AGENT,
    target_base_url,
)
from src import metrics  # noqa: E402

DEFAULT_PORT = 9113
DEFAULT_SAMPLE_SIZE = 300  # product ids 1..300 -- covers all 6 defect types, see module docstring


def run_and_serve(client_id=None, port=DEFAULT_PORT, sample_size=DEFAULT_SAMPLE_SIZE):
    """Run the instrumented sample crawl described in this module's
    docstring, then start `prometheus_client`'s `/metrics` HTTP server on
    `port` and block until interrupted.

    `client_id`: identity for the MAIN crawl client (default: generate one).
    `port`: TCP port to serve `/metrics` on.
    `sample_size`: how many low-numbered product ids (1..sample_size) to
    crawl for the main sample.

    Must call `metrics.build_registry()` (or equivalent) before doing any
    fetching, so the `record_*`/`set_*` helpers have real metric objects to
    write to.
    """
    raise NotImplementedError


if __name__ == "__main__":
    run_and_serve()
