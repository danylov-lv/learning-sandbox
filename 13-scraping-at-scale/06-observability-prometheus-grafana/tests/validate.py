"""Validator for 13-scraping-at-scale task 06 -- observability (Prometheus/Grafana).

Two things are checked, both described in `.authoring/design.md`'s
"Verification philosophy" section for task 06:

  MUST-PASS, direct (no Prometheus/Grafana required):
    1. Launch the learner's `src/serve.py` as a real SUBPROCESS (it must run
       an instrumented sample crawl against the target and then serve
       `prometheus_client`'s `/metrics` on port 9113). Poll
       `GET http://127.0.0.1:9113/metrics` until it responds.
    2. Parse the Prometheus text exposition
       (`prometheus_client.parser.text_string_to_metric_families`) and
       assert: all required metric families are present; the pages-fetched
       counter has BOTH strategy=html and strategy=api greater than zero;
       the quarantine counter moved for at least two distinct defect
       reasons; the field-completeness gauge has multiple field labels; the
       latency histogram has real observations (`_count` > 0) plus its
       standard `_bucket`/`_sum` series.
    3. The learner's `dashboards/spider.json` exists, parses as JSON, has a
       `panels` array, and its panels' queries reference at least 3 of the
       required metric names.

  SKIP-IF-DOWN (never fails the task on its own -- prints a NOTICE and
  continues): `harness.query_prometheus('up{job="spider"}')` -- if
  Prometheus is reachable AND has already scraped the learner's endpoint,
  assert the value is 1; a sample metric query; Grafana `/api/health`.

Run from this task's directory:

    uv run python tests/validate.py
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    _last_line,
    grafana_base_url,
    guarded,
    not_passed,
    passed,
    query_prometheus,
)

METRICS_PORT = 9113
METRICS_URL = f"http://127.0.0.1:{METRICS_PORT}/metrics"
STARTUP_POLL_TIMEOUT_S = 120.0  # generous: a paced ~600-request sample crawl can legitimately take tens of seconds
STARTUP_POLL_INTERVAL_S = 0.5
PROM_WAIT_TOTAL_S = 20.0  # how long we keep the subprocess alive waiting for a Prometheus scrape (scrape_interval=5s)
PROM_WAIT_INTERVAL_S = 2.0

REQUIRED_FAMILIES_STRICT = {
    "spider_pages_fetched",
    "spider_records_quarantined",
    "spider_fetch_errors",
    "spider_fetch_latency_seconds",
    "spider_field_completeness",
}
# The task brief allows either (or both) of these two ban/honeypot signals --
# see src/metrics.py's docstring ("and/or").
BAN_OR_HONEYPOT_FAMILIES = {"spider_banned", "spider_honeypot_hits"}

KNOWN_DEFECT_REASONS = {
    "missing_price",
    "price_na",
    "empty_title",
    "negative_price",
    "bad_currency",
    "truncated",
}
MIN_DISTINCT_QUARANTINE_REASONS = 2

MIN_DISTINCT_COMPLETENESS_FIELDS = 2

DASHBOARD_PATH = TASK_ROOT / "dashboards" / "spider.json"
DASHBOARD_METRIC_TOKENS = [
    "spider_pages_fetched_total",
    "spider_records_quarantined_total",
    "spider_fetch_errors_total",
    "spider_fetch_latency_seconds",
    "spider_field_completeness",
    "spider_banned",
    "spider_honeypot_hits_total",
]
MIN_DASHBOARD_METRICS_REFERENCED = 3


def _port_already_in_use(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _launch_serve_subprocess():
    cmd = [sys.executable, str(TASK_ROOT / "src" / "serve.py")]
    env = os.environ.copy()
    return subprocess.Popen(
        cmd, cwd=str(TASK_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def _poll_metrics_endpoint(proc):
    """Poll GET /metrics until it responds or the subprocess exits/times out.
    Returns the response text. NOT PASSED (clean, single line) on failure."""
    import httpx

    deadline = time.monotonic() + STARTUP_POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            not_passed(
                f"src/serve.py exited early (code {proc.returncode}) before serving /metrics -- "
                f"{_last_line(out)}"
            )
        try:
            resp = httpx.get(METRICS_URL, timeout=2.0)
            if resp.status_code == 200 and resp.text.strip():
                return resp.text
        except httpx.HTTPError:
            pass
        time.sleep(STARTUP_POLL_INTERVAL_S)

    not_passed(
        f"src/serve.py never served a working /metrics on port {METRICS_PORT} within "
        f"{STARTUP_POLL_TIMEOUT_S:.0f}s -- is run_and_serve() implemented and does it call "
        f"start_http_server()/equivalent after the sample crawl finishes?"
    )


def _parse_metrics(text):
    from prometheus_client.parser import text_string_to_metric_families

    family_names = set()
    samples_by_name = {}
    for fam in text_string_to_metric_families(text):
        family_names.add(fam.name)
        for s in fam.samples:
            samples_by_name.setdefault(s.name, []).append(s)
    return family_names, samples_by_name


def _check_families(family_names):
    missing = REQUIRED_FAMILIES_STRICT - family_names
    if missing:
        not_passed(
            f"/metrics is missing required metric famil{'y' if len(missing) == 1 else 'ies'}: "
            f"{sorted(missing)} (found: {sorted(family_names)})"
        )
    if not (BAN_OR_HONEYPOT_FAMILIES & family_names):
        not_passed(
            "/metrics must expose at least one of spider_banned / spider_honeypot_hits_total "
            f"(found: {sorted(family_names)})"
        )


def _check_pages_fetched(samples_by_name):
    rows = samples_by_name.get("spider_pages_fetched_total", [])
    by_strategy = {s.labels.get("strategy"): s.value for s in rows}
    for strategy in ("html", "api"):
        if by_strategy.get(strategy, 0) <= 0:
            not_passed(
                f"spider_pages_fetched_total{{strategy=\"{strategy}\"}} did not move "
                f"(got {by_strategy.get(strategy)!r}) -- the sample crawl must fetch both "
                f"GET /product/{{id}} (html) and GET /api/product/{{id}} (api)"
            )
    return by_strategy


def _check_quarantine(samples_by_name):
    rows = samples_by_name.get("spider_records_quarantined_total", [])
    nonzero_reasons = {s.labels.get("reason") for s in rows if s.value > 0}
    known_hit = nonzero_reasons & KNOWN_DEFECT_REASONS
    if len(known_hit) < MIN_DISTINCT_QUARANTINE_REASONS:
        not_passed(
            f"spider_records_quarantined_total only moved for {sorted(known_hit)} known defect "
            f"reason(s) (need >= {MIN_DISTINCT_QUARANTINE_REASONS} of {sorted(KNOWN_DEFECT_REASONS)}) "
            f"-- the sample crawl's id range must include several bad-record ids "
            f"(see data/ground-truth.json's bad_records.by_defect)"
        )
    return known_hit


def _check_completeness(samples_by_name):
    rows = samples_by_name.get("spider_field_completeness", [])
    fields = {s.labels.get("field") for s in rows}
    bad_ratio = [s for s in rows if not (0.0 <= s.value <= 1.0)]
    if bad_ratio:
        not_passed(
            f"spider_field_completeness has a value outside [0,1]: "
            f"{[(s.labels, s.value) for s in bad_ratio]}"
        )
    if len(fields) < MIN_DISTINCT_COMPLETENESS_FIELDS:
        not_passed(
            f"spider_field_completeness only has {sorted(fields)} field label(s), need >= "
            f"{MIN_DISTINCT_COMPLETENESS_FIELDS}"
        )
    return fields


def _check_latency(samples_by_name):
    count_rows = samples_by_name.get("spider_fetch_latency_seconds_count", [])
    bucket_rows = samples_by_name.get("spider_fetch_latency_seconds_bucket", [])
    sum_rows = samples_by_name.get("spider_fetch_latency_seconds_sum", [])
    if not bucket_rows or not sum_rows or not count_rows:
        not_passed(
            "spider_fetch_latency_seconds is missing its _bucket/_count/_sum series -- "
            "is it declared as a prometheus_client.Histogram?"
        )
    total_count = sum(s.value for s in count_rows)
    if total_count <= 0:
        not_passed(
            "spider_fetch_latency_seconds_count is 0 -- no latency observations were recorded "
            "during the sample crawl (call .observe() / record_fetch() around every fetch)"
        )
    return total_count


def _check_dashboard():
    if not DASHBOARD_PATH.exists():
        not_passed(
            f"dashboard not found at {DASHBOARD_PATH.relative_to(MODULE_ROOT)} -- build a Grafana "
            f"dashboard JSON there (see the task README) and, to see it live, copy it to "
            f"../docker/grafana/dashboards/"
        )
    try:
        data = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        not_passed(f"dashboards/spider.json is not valid JSON: {e}")
    panels = data.get("panels")
    if not isinstance(panels, list) or not panels:
        not_passed("dashboards/spider.json has no non-empty 'panels' array")

    blob = json.dumps(panels)
    referenced = {name for name in DASHBOARD_METRIC_TOKENS if name in blob}
    if len(referenced) < MIN_DASHBOARD_METRICS_REFERENCED:
        not_passed(
            f"dashboards/spider.json panels only reference {sorted(referenced)} required metric "
            f"name(s), need >= {MIN_DASHBOARD_METRICS_REFERENCED} of {DASHBOARD_METRIC_TOKENS}"
        )
    return referenced


def _check_prometheus_live():
    """SKIP-IF-DOWN: never fails the task. Returns a short status string."""
    for _ in range(int(PROM_WAIT_TOTAL_S / PROM_WAIT_INTERVAL_S)):
        result = query_prometheus('up{job="spider"}')
        if result is None:
            return "SKIPPED (Prometheus unreachable)"
        data = result.get("data", {}).get("result", [])
        if data:
            value = data[0].get("value", [None, None])[1]
            if value != "1":
                # SKIP-IF-DOWN, per design.md: Prometheus may have the spider
                # target registered but not yet have a successful scrape (the
                # learner's serve.py binds /metrics only after its crawl, and
                # scrapes land on a 5s interval). This is never a hard failure
                # -- the MUST-PASS signal is the /metrics content checked above.
                return (
                    f"SKIPPED (up{{job=\"spider\"}}={value!r}: target registered but not "
                    f"scraped successfully yet)"
                )
            sample = query_prometheus("spider_pages_fetched_total")
            sample_ok = bool(sample and sample.get("data", {}).get("result"))
            return f"scraped OK (up=1, sample query {'returned data' if sample_ok else 'empty'})"
        time.sleep(PROM_WAIT_INTERVAL_S)
    return "SKIPPED (Prometheus reachable but had not scraped host.docker.internal:9113 in time)"


def _check_grafana_live():
    """SKIP-IF-DOWN: never fails the task. Returns a short status string."""
    import httpx

    try:
        resp = httpx.get(grafana_base_url() + "/api/health", timeout=3.0)
        if resp.status_code == 200:
            return "reachable"
        return f"SKIPPED (unexpected status {resp.status_code})"
    except httpx.HTTPError:
        return "SKIPPED (Grafana unreachable)"


@guarded
def main():
    if _port_already_in_use(METRICS_PORT):
        not_passed(
            f"port {METRICS_PORT} is already in use -- stop any previously running "
            f"`serve.py` (or other process bound to it) before running the validator"
        )

    proc = _launch_serve_subprocess()
    try:
        text = _poll_metrics_endpoint(proc)
        family_names, samples_by_name = _parse_metrics(text)

        _check_families(family_names)
        by_strategy = _check_pages_fetched(samples_by_name)
        reasons = _check_quarantine(samples_by_name)
        fields = _check_completeness(samples_by_name)
        total_latency_count = _check_latency(samples_by_name)
        referenced = _check_dashboard()

        prom_status = _check_prometheus_live()
        grafana_status = _check_grafana_live()
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    passed(
        f"pages_fetched html={by_strategy.get('html')} api={by_strategy.get('api')}; "
        f"quarantine reasons moved={sorted(reasons)}; "
        f"completeness fields={sorted(fields)}; "
        f"latency observations={total_latency_count:.0f}; "
        f"dashboard references={sorted(referenced)}; "
        f"Prometheus: {prom_status}; Grafana: {grafana_status}"
    )


if __name__ == "__main__":
    main()
