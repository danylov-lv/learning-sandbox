"""s13.t06 -- Prometheus metric definitions for the instrumented spider.

This module declares the metric OBJECTS that `src/serve.py`'s crawl updates
and that `prometheus_client` exposes as text exposition on `/metrics`. Get
the NAMES and LABEL SETS exactly right -- both `tests/validate.py` and the
module's Prometheus `spider` scrape job (`docker/prometheus/prometheus.yml`)
assume these exact strings. Renaming or relabeling any of them breaks the
validator and the provisioned Grafana dashboard alike.

Required metric families (do not rename):

  spider_pages_fetched_total{strategy}       Counter
      strategy in {"html", "api"} -- one increment per successful fetch of
      GET /product/{id} (strategy="html") or GET /api/product/{id}
      (strategy="api"). Both label values must move under a real run so a
      dashboard panel can compare fetch volume by strategy.

  spider_records_quarantined_total{reason}   Counter
      One increment per record your crawl decides to quarantine (fails a
      basic data-quality check), labeled by WHY. Use the same defect-type
      vocabulary the target's bad records use: "missing_price", "price_na",
      "empty_title", "negative_price", "bad_currency", "truncated" (see the
      module README / task README for what each means). A record can fail
      more than one check -- decide whether you count it once per record or
      once per failed check, and document your choice.

  spider_fetch_errors_total{reason}          Counter
      One increment per failed fetch (non-2xx status, timeout, connection
      error, JSON-decode failure, ...), labeled by a short reason string you
      choose (e.g. "http_404", "timeout").

  spider_fetch_latency_seconds               Histogram
      Per-request wall-clock latency in seconds, observed around every
      fetch (html or api). An optional "strategy" label is fine but not
      required -- the validator only checks that the histogram family
      exists with the standard `_bucket`/`_count`/`_sum` series.

  spider_field_completeness{field}           Gauge
      One time series per tracked field name (e.g. "price", "title",
      "currency", "rating", "shipping_info") holding the FRACTION (0.0-1.0)
      of this run's sampled records where that field was present/valid.
      Recompute and set this after the sample finishes (or update it
      incrementally -- either is fine, the exposed value at scrape time is
      what matters).

  spider_banned                              Gauge (0 or 1)
      Whether the client used for the run is currently banned by the
      target (per `GET /__debug/client`'s `banned` field, or your own
      tracking of a 403 you triggered on purpose). See `serve.py`'s
      docstring for why this should NOT be the same client id you use for
      the main sample crawl.

  spider_honeypot_hits_total                 Counter
      Total honeypot trips (a request that landed on a trap product id or
      /trap/{token}) this process has made, across its whole lifetime.

Everything below is a stub: the six metric objects are `None` placeholders
and every helper function `raise NotImplementedError`. Replace the
placeholders with real `prometheus_client.Counter` / `Gauge` / `Histogram`
instances (see the `prometheus_client` docs for the constructor shapes --
name, documentation string, and `labelnames=[...]` for the labeled ones),
and fill in the helper bodies so `serve.py` has one place to call into
instead of touching the six objects directly.
"""

from prometheus_client import CollectorRegistry  # noqa: F401  (only needed if you build_registry() with a custom registry)

# --------------------------------------------------------------------------
# Metric objects -- TODO: replace each `None` with the real
# prometheus_client Counter/Gauge/Histogram, either here at import time or
# inside build_registry() below (your choice, but build_registry() must
# leave these names populated before serve.py starts scraping them).
# --------------------------------------------------------------------------

PAGES_FETCHED = None  # Counter "spider_pages_fetched_total", labelnames=["strategy"]
RECORDS_QUARANTINED = None  # Counter "spider_records_quarantined_total", labelnames=["reason"]
FETCH_ERRORS = None  # Counter "spider_fetch_errors_total", labelnames=["reason"]
FETCH_LATENCY = None  # Histogram "spider_fetch_latency_seconds"
FIELD_COMPLETENESS = None  # Gauge "spider_field_completeness", labelnames=["field"]
BANNED = None  # Gauge "spider_banned"
HONEYPOT_HITS = None  # Counter "spider_honeypot_hits_total"


def build_registry(registry=None):
    """Instantiate all seven metric objects above and assign them to the
    module-level names (`PAGES_FETCHED`, ... `HONEYPOT_HITS`), then return
    the registry they were registered into.

    `registry`: an optional `prometheus_client.CollectorRegistry` to
    register the metrics into instead of prometheus_client's implicit
    global default registry (`prometheus_client.REGISTRY`). Passing a fresh
    registry per call is useful if you ever want to build this module's
    metrics more than once in the same process (e.g. from a test) without
    hitting prometheus_client's "duplicated timeseries" error on the
    second `Counter(...)` call with the same name. `serve.py` only needs
    to call this ONCE per process, before it starts the `/metrics` HTTP
    server.

    Call this before any of the `record_*` / `set_*` helpers below --
    they assume the module-level metric objects are already real
    prometheus_client instances, not `None`.
    """
    raise NotImplementedError


def record_fetch(strategy, seconds):
    """Record one successful fetch: increment
    `PAGES_FETCHED.labels(strategy=strategy)` and observe `seconds` on
    `FETCH_LATENCY`. `strategy` is "html" or "api"."""
    raise NotImplementedError


def record_quarantine(reason):
    """Increment `RECORDS_QUARANTINED.labels(reason=reason)` for one
    quarantined record. `reason` should be one of the six defect-type
    strings documented at the top of this module."""
    raise NotImplementedError


def record_error(reason):
    """Increment `FETCH_ERRORS.labels(reason=reason)` for one failed
    fetch attempt."""
    raise NotImplementedError


def set_field_completeness(field, ratio):
    """Set `FIELD_COMPLETENESS.labels(field=field)` to `ratio` (a float in
    [0.0, 1.0])."""
    raise NotImplementedError


def set_banned(is_banned):
    """Set the `BANNED` gauge to 1 if `is_banned` is truthy, else 0."""
    raise NotImplementedError


def record_honeypot_hit():
    """Increment `HONEYPOT_HITS` by 1."""
    raise NotImplementedError
