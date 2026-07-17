# Module 13 — task-authoring + live verification notes

Second (task-authoring) wave, after the wave-1 infra build (see
`notes-infra.md`). Stack left running from wave-1 (target :8313 healthy,
Prometheus :9313, Grafana :3313); all verification ran against it live.

## What this wave did

A prior interrupted session had authored tasks 01–05 and a partial 06 but
never committed, never updated `GENERATION_STATE.md`, and left two tasks
mid-verification with throwaway reference impls in place. This session
inherited that on-disk state, decontaminated it, completed the module, and
verified everything live.

- **Decontamination**: tasks 01 (`src/recon.py`, `RECON.md`) and 05
  (`src/costmodel.py`, `src/router.py`, `ANALYSIS.md`) still held
  self-labelled "THROWAWAY reference" fills from the prior session. Task
  05 had `.stub` siblings — restored those. Task 01 had none — its stub
  (`recon.py` = 3 `NotImplementedError` fns + docstrings; `RECON.md` = the
  4-section `[fill in` template) was reconstructed from the README/validator
  contract. 02/03/04 were confirmed clean stubs (never contaminated).
- **Verification (all live, throwaway refs reverted byte-identical, none
  committed)**:
  - 01 recon — PASS: 4000 real ids, 0 honeypots, banned=False,
    rate_limit_violations=0, 40 sample records match the catalog oracle
    incl. js-only rating/shipping_info. Fail-path: stub → NOT PASSED.
  - 02 data-quality — PASS: quarantine == exactly 400 bad ids across 6
    defect types, clean == exactly 3600; truncation signal is the literal
    `[TRNC]` substring (unspecified in the README on purpose).
  - 03 change-detection — PASS: day0→day1 exact (120/120 on a 240 sample),
    negative control stable across all 4 markup versions, nonce stripped,
    616 requests / 0 violations.
  - 04 markup-resilience — PASS: 200 products × 4 forced versions, 1.000
    completeness per version; per-field fallback chains, no version
    special-cased.
  - 05 budget-router — PASS on the code (costmodel + router): completeness
    1.0 ≥ 0.98, n_rendered=1191, modeled_cost=12337.0 == committed
    `mixed_cost` bit-for-bit; the only earlier miss was a throwaway
    ANALYSIS.md 7 chars under the 1200 min (deliverable length, not code).
  - 06 observability — completed (README, hints 1–3, NOTES, `dashboards/
    .gitkeep`) and PASS: `/metrics` families/labels all move under a paced
    two-client sample crawl (main + one deliberate honeypot client);
    `dashboards/spider.json` panel check. See the validator fix below.
  - 07 capstone (new) — CP1 steady (day 0), CP2 chaos-markup + change
    detection + idempotency, CP3 DESIGN.md + CP1/CP2 subprocess re-run. All
    three PASS on a throwaway reference; CP1 modeled_cost=12337.0 reproduces
    `mixed_cost` exactly. Stubs (pipeline/changedetect/metrics = 6/3/8
    `NotImplementedError`) + unfilled DESIGN.md (7 sections) reverted.
  - k8s-bonus (new) — `spider-platform` Helm chart skeleton (empty
    templates + `.gitkeep`), README/hints/NOTES, validator runs `helm lint`
    + `helm template` and asserts a resource-bounded spider Deployment with
    liveness+readiness probes, a matching HPA, and a PDB. helm v3.18.2 is
    present; kind/k3d are NOT, so verification is template/lint only (live
    cluster deploy is the optional stretch, same as modules 06/07). Fails
    on the empty skeleton, passes on a throwaway fill, reverted.

## Bug fixed this wave

`06/tests/validate.py` `_check_prometheus_live` was documented "SKIP-IF-DOWN:
never fails the task" but called `not_passed(...)` when `up{job="spider"}`
returned a value other than `"1"` — contradicting design.md's rule that
Prometheus/Grafana live checks are ALWAYS skip-if-down. A natural
crawl-then-serve learner solution binds `/metrics` only after its crawl, so
Prometheus (5s scrape interval) can legitimately read `up=0` at query time
and the learner would fail on a live check that was never meant to be a hard
gate. Fixed: `up != "1"` now returns a `SKIPPED (...)` status string instead
of failing. The MUST-PASS signal remains the learner's own `/metrics`
content (families/labels/histogram/dashboard), all unaffected.

## Reusable gotchas surfaced (baked into hints/docstrings)

- prometheus_client: a labelled Counter/Gauge never `.labels(...)`-touched
  still emits `# HELP`/`# TYPE` (family visible to
  `text_string_to_metric_families`) but zero samples — relied on so CP1 can
  require `spider_fetch_errors` as a present family on a clean, error-free
  run.
- `build_registry()` must be idempotent across repeated `run_pipeline`
  calls in one process (capstone CP2 calls the pipeline twice) — else the
  second `Counter(...)` hits "duplicated timeseries".
- Markup v1 renders price `"{CUR} {AMT}"`; v2's visible `.display-price`
  renders `"{AMT} {CUR}"` (amount-first) — a fallback chain reusing one
  token-order assumption across both breaks silently.
- Under `chaos=True` the markup version cycles by wall-clock for ALL
  products at once (not per-product), so a crawler inferring version from
  `product_id % 4` degrades only during CP2, never CP1.

## Stock state after this wave

All learner `src/` are `NotImplementedError` stubs; all deliverable docs
(`RECON.md`, `ANALYSIS.md`, every `DESIGN.md`, `NOTES.md`) ship unfilled;
`dashboards/` holds only `.gitkeep`; k8s templates are empty placeholders.
No reference solutions, `run/`/`sinks/`/`scratch`, `*-local.json`, or
`__pycache__` committed. `data/` = gitignored catalog.json/target-spec.json
+ committed ground-truth.json (sha 335e94ca…80df0, unchanged). Stack left
running — `docker compose down -v` for a cold stock state.
