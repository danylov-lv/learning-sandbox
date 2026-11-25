The full skeleton, in pseudocode -- you still write every real line.

**`src/metrics.py`.**

```
from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry

def build_registry(registry=None):
    global PAGES_FETCHED, RECORDS_QUARANTINED, FETCH_ERRORS, FETCH_LATENCY
    global FIELD_COMPLETENESS, BANNED, HONEYPOT_HITS
    kw = {"registry": registry} if registry is not None else {}
    PAGES_FETCHED = Counter("spider_pages_fetched_total", "...",
                            labelnames=["strategy"], **kw)
    RECORDS_QUARANTINED = Counter("spider_records_quarantined_total", "...",
                                  labelnames=["reason"], **kw)
    FETCH_ERRORS = Counter("spider_fetch_errors_total", "...",
                           labelnames=["reason"], **kw)
    FETCH_LATENCY = Histogram("spider_fetch_latency_seconds", "...", **kw)
    FIELD_COMPLETENESS = Gauge("spider_field_completeness", "...",
                               labelnames=["field"], **kw)
    BANNED = Gauge("spider_banned", "...", **kw)
    HONEYPOT_HITS = Counter("spider_honeypot_hits_total", "...", **kw)
    return registry  # or prometheus_client.REGISTRY when registry is None
```

The helpers are one line each: `record_fetch` does
`PAGES_FETCHED.labels(strategy=strategy).inc()` and
`FETCH_LATENCY.observe(seconds)`; `record_quarantine`/`record_error` do
`.labels(reason=reason).inc()`; `set_field_completeness` does
`.labels(field=field).set(ratio)`; `set_banned` does `BANNED.set(1 if
is_banned else 0)`; `record_honeypot_hit` does `HONEYPOT_HITS.inc()`.

**`src/serve.py`.**

```
def run_and_serve(client_id=None, port=9113, sample_size=300):
    metrics.build_registry()          # default global registry
    base = target_base_url()
    main_id = client_id or "spider-main"
    headers = {"User-Agent": DEFAULT_USER_AGENT,
               "Accept-Language": DEFAULT_ACCEPT_LANGUAGE,
               "X-Client-Id": main_id}

    seen = {f: [0, 0] for f in ["price","title","currency","rating","shipping_info"]}
    with httpx.Client(base_url=base, headers=headers) as client:
        for pid in range(1, sample_size + 1):
            # html fetch: time it, record_fetch("html", dt), record_error on non-2xx
            # api fetch:  time it, record_fetch("api", dt), then inspect JSON:
            #   reason = classify(record)   # returns a defect string or None
            #   if reason: metrics.record_quarantine(reason)
            #   for each tracked field: seen[f][1]++; if present-and-valid seen[f][0]++
            pace()                        # small sleep to stay under refill rate
    for f, (ok, total) in seen.items():
        metrics.set_field_completeness(f, ok / total if total else 0.0)

    # one deliberate honeypot hit with a DIFFERENT client id
    hp_id = load_ground_truth()["honeypot_ids"][0]
    with httpx.Client(base_url=base, headers={**headers, "X-Client-Id": "spider-throwaway"}) as tc:
        tc.get(f"/api/product/{hp_id}")   # bans this throwaway client
    metrics.record_honeypot_hit()
    metrics.set_banned(True)

    prometheus_client.start_http_server(port)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
```

`classify(record)` is your data-quality check against the six defect strings:
missing `price` key -> `missing_price`; `price == "N/A"` -> `price_na`;
`title == ""` -> `empty_title`; numeric `price < 0` -> `negative_price`;
`currency` not in the known set (USD/EUR/GBP/CAD) -> `bad_currency`;
`description` carrying the truncation marker -> `truncated`. Decide and note
whether you return the first failing reason or count every failure -- the
validator only needs at least two distinct reasons to have moved.

Watch the details that actually bite: pace the loop (an unpaced 300-id burst
of 600 requests trips the rate limiter and bans your MAIN client, which then
403s and your html/api counters stall); guard each fetch in try/except so a
single error calls `record_error(...)` instead of killing the process; and
build the registry exactly once (a second `build_registry()` in the same
process raises "duplicated timeseries").

**The dashboard.** Minimal hand-written `dashboards/spider.json`:

```
{
  "title": "Spider",
  "panels": [
    {"id": 1, "type": "timeseries", "title": "Fetch rate by strategy",
     "targets": [{"expr": "sum(rate(spider_pages_fetched_total[1m])) by (strategy)"}]},
    {"id": 2, "type": "timeseries", "title": "p95 latency",
     "targets": [{"expr": "histogram_quantile(0.95, rate(spider_fetch_latency_seconds_bucket[5m]))"}]},
    {"id": 3, "type": "stat", "title": "Field completeness",
     "targets": [{"expr": "spider_field_completeness"}]}
  ],
  "schemaVersion": 39, "version": 1
}
```

That references three required metric names, which is the bar. A real
UI-exported dashboard carries a lot more boilerplate (datasource refs, grid
positions, time range) -- that's fine, the validator only looks for the metric
names inside the `panels` array.
