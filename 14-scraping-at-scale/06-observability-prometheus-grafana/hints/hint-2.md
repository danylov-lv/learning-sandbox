Concrete guidance per piece, still without handing you the file.

**Building the metrics.** Each `prometheus_client` metric takes a name, a
documentation string, and (for labeled ones) `labelnames=[...]`. A labeled
metric is not usable until you pick a label value:
`PAGES_FETCHED.labels(strategy="html").inc()`. A Gauge with a label works the
same way (`.labels(field="price").set(0.97)`); an unlabeled Gauge is just
`BANNED.set(1)`. A Histogram is `.observe(seconds)`. Have `build_registry()`
assign the seven objects to the module-level names and return the registry.
One subtlety: if you construct the same metric name twice in one process you
get a "duplicated timeseries" error -- that's why `build_registry()` takes an
optional `registry` argument and why `serve.py` should call it exactly once.
For the default global registry, `start_http_server(port)` exposes everything
automatically; if you build into a custom `CollectorRegistry`, you expose it
with `prometheus_client.make_wsgi_app(registry)` behind a tiny WSGI server
instead.

**Exposing /metrics.** The simplest path is
`prometheus_client.start_http_server(9113)` -- it spins up a background thread
serving `/metrics` from the default registry, then your main thread just needs
to block (a bare `while True: time.sleep(...)`, or catch `KeyboardInterrupt`)
so the process stays alive for Prometheus to scrape repeatedly. Do the crawl
FIRST, then start the server, then block -- the validator polls until
`/metrics` responds, so a slow crawl in front of it is fine, but the server
must eventually come up.

**The paced sample crawl.** Loop ids 1..300 with your main client (browser
`User-Agent` + `Accept-Language` + a stable `X-Client-Id`). Per id: time and
fetch `GET /product/{id}` as `strategy="html"`, time and fetch
`GET /api/product/{id}` as `strategy="api"`, recording both latencies. Pace so
you stay under the target's refill rate -- 300 ids is small, a modest sleep
between requests (or an explicit rate cap) keeps you far from the ban
threshold. The JSON from the API endpoint is where you inspect field validity.

**Quarantine vocabulary.** Use the target's own six defect-type strings as
your `reason` labels: `missing_price` (no price key), `price_na` (price is the
string "N/A"), `empty_title` (title is ""), `negative_price` (price < 0),
`bad_currency` (currency is an unknown code like "XYZ"), `truncated`
(description was cut and carries a truncation marker). Check the API JSON
against each and `record_quarantine(reason)` on a failure. The validator wants
at least two distinct reasons to have moved -- ids 1..300 already contain
several bad records, so a correct check surfaces more than two.

**Completeness.** Track, across the sample, the fraction of records where each
of a few fields (`price`, `title`, `currency`, `rating`, `shipping_info`) is
present and valid, then `set_field_completeness(field, fraction)` per field
after the loop. Every value must land in [0, 1].

**Ban/honeypot.** After the main loop, make ONE request with a DIFFERENT,
throwaway client id to a honeypot id from `data/ground-truth.json`, then call
`record_honeypot_hit()` and `set_banned(True)`.

**The dashboard.** In Grafana (`http://localhost:3313`) add a time-series
panel with `sum(rate(spider_pages_fetched_total[1m])) by (strategy)`, a second
with `histogram_quantile(0.95,
rate(spider_fetch_latency_seconds_bucket[5m]))`, a stat panel on
`spider_field_completeness`, then export the dashboard JSON to
`dashboards/spider.json`. That already references three metrics.
