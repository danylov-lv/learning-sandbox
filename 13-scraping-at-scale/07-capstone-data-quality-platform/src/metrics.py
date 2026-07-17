"""s13.t07 -- Prometheus instrumentation for the capstone pipeline.

Same seven metric families task 06 built, reused here so `pipeline.py`'s
`run_pipeline` can be observed the same way a real scraping operator would
watch it -- fetch volume by strategy, why records get quarantined, how slow
fetches are getting, per-field completeness, and whether the client is
banned or has hit a honeypot. Unlike task 06, nothing here needs to bind an
HTTP `/metrics` port or run as a subprocess: `tests/validate_cp1.py` reads
this module's registry directly with `prometheus_client.generate_latest`,
in-process, right after a `run_pipeline` call returns. Get the metric NAMES
and LABEL SETS exactly right -- the validator asserts on these exact
strings, same convention as task 06:

  spider_pages_fetched_total{strategy}       Counter
      strategy in {"html", "api"} -- one increment per successful fetch of
      GET /product/{id} (strategy="html") or GET /api/product/{id}
      (strategy="api").

  spider_records_quarantined_total{reason}   Counter
      One increment per record `run_pipeline` quarantines, labeled by the
      defect-type vocabulary from `quality_check()` in pipeline.py:
      "missing_price", "price_na", "empty_title", "negative_price",
      "bad_currency", "truncated".

  spider_fetch_errors_total{reason}          Counter
      One increment per failed fetch (non-2xx, timeout, parse failure, ...),
      labeled by a short reason string of your choice.

  spider_fetch_latency_seconds               Histogram
      Per-request wall-clock latency, observed around every fetch (html or
      api).

  spider_field_completeness{field}           Gauge
      Fraction (0.0-1.0) of a run's records where a tracked field
      (`price`, `title`, `currency`, `rating`, `shipping_info`, ...) was
      present/valid. Set (or update) after a `run_pipeline` call finishes.

  spider_banned                              Gauge (0 or 1)
      Whether the client used for the run is currently banned by the
      target, per `GET /__debug/client`'s `banned` field.

  spider_honeypot_hits_total                 Counter
      Total honeypot trips this process has made. Should stay at 0 for
      every `run_pipeline` call -- the pipeline must never touch a
      honeypot id or `/trap/*` in the first place; this metric exists so a
      regression would be VISIBLE, not so it's expected to move.

Everything below is a stub. `REGISTRY` and the six metric objects are
`None` placeholders; every helper `raise NotImplementedError`.

IMPORTANT: `run_pipeline` in `pipeline.py` can be called more than once in
the same process (CP1 calls it once; CP2 calls it twice, under chaos, for
two different days). `build_registry()` MUST be safe to call more than once
without raising `prometheus_client`'s "Duplicated timeseries in
CollectorRegistry" error on the second call -- guard it (e.g. a
module-level flag that makes a second call a no-op and just returns the
already-built `REGISTRY`), don't re-instantiate the six metric objects if
they already exist.
"""

REGISTRY = None  # prometheus_client.CollectorRegistry -- set by build_registry()

PAGES_FETCHED = None  # Counter "spider_pages_fetched_total", labelnames=["strategy"]
RECORDS_QUARANTINED = None  # Counter "spider_records_quarantined_total", labelnames=["reason"]
FETCH_ERRORS = None  # Counter "spider_fetch_errors_total", labelnames=["reason"]
FETCH_LATENCY = None  # Histogram "spider_fetch_latency_seconds"
FIELD_COMPLETENESS = None  # Gauge "spider_field_completeness", labelnames=["field"]
BANNED = None  # Gauge "spider_banned"
HONEYPOT_HITS = None  # Counter "spider_honeypot_hits_total"


def build_registry():
    """Instantiate all seven metric objects above, register them into a
    `prometheus_client.CollectorRegistry`, assign that registry to the
    module-level `REGISTRY` name, and return it.

    Must be idempotent: a second (or third, ...) call in the same process
    must NOT raise "Duplicated timeseries in CollectorRegistry" -- either
    short-circuit if `REGISTRY` is already built, or otherwise ensure the
    six metric objects are only ever constructed once per process.

    `pipeline.run_pipeline` calls this once at the start of every call (it
    may be called more than once per process -- see module docstring).
    """
    raise NotImplementedError


def record_fetch(strategy, seconds):
    """Increment `PAGES_FETCHED.labels(strategy=strategy)` and observe
    `seconds` on `FETCH_LATENCY`. `strategy` is "html" or "api"."""
    raise NotImplementedError


def record_quarantine(reason):
    """Increment `RECORDS_QUARANTINED.labels(reason=reason)` for one
    quarantined record."""
    raise NotImplementedError


def record_error(reason):
    """Increment `FETCH_ERRORS.labels(reason=reason)` for one failed fetch
    attempt."""
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
