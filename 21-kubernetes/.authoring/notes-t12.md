# Notes for task 12 (services-and-dns-debugging) -- authoring record

## Defects chosen

One healthy Deployment `catalog-backend` (image `sandbox20-app:1.0`, 2
replicas, correct readinessProbe on its real port 8080) fronted by three
independently broken Services, all meant to expose it on port 80:

1. `catalog` -- **selector mismatch** (`selector: {app: catalog}` vs pods
   labeled `app: catalog-backend`). Zero Endpoints. Diagnosable purely from
   `kubectl get endpoints catalog`.
2. `catalog-batch` -- **wrong targetPort** (`targetPort: 9090`, app
   actually listens on 8080). Endpoints are populated (selector is
   correct) but advertise the wrong port -- diagnosable by comparing
   `kubectl get endpoints` output against the Deployment's real
   `containerPort`.
3. `catalog-peer` -- **headless vs ClusterIP misuse**, chosen as the
   *reverse* direction from design.md's one-line example ("client expects
   a stable VIP" reads as ClusterIP-wrongly-made-headless, which is what I
   built: `clusterIP: None` on a Service that should behave like an
   ordinary load-balanced entrypoint). I verified live (see below) that
   this does NOT need any bespoke "compare resolved IP to clusterIP" logic
   -- headless Services bypass kube-proxy's port-translation (DNAT)
   entirely, so a client connecting to the *Service's declared port* (80)
   against a headless Service's resolved address (a raw pod IP) gets
   "connection refused" because nothing listens on port 80 on the pod
   itself (only 8080 does). This is a clean, deterministic, real failure
   mode, not a synthetic assertion.

All three: selector/endpoints and clusterIP fields are independently
checkable via `kubectl get endpoints` / `kubectl describe svc` /
`kubectl get svc -o jsonpath`, matching the "independently diagnosable"
requirement.

## Live verification of the headless/DNS behavior (before committing to the design)

Built a throwaway `zz-verify` namespace with a 2-replica backend + 3
Services (good ClusterIP, selector-mismatch, headless) plus a `dnstest`
pod running `sandbox20-app:1.0` (python3 stdlib only, no curl/wget needed).
Confirmed via `socket.gethostbyname`/`getaddrinfo` and `urllib.request`:

- Normal ClusterIP Service: DNS resolves to the Service's own ClusterIP
  (single, stable address); curl on `port: 80` succeeds (kube-proxy DNATs
  to the pod's real port).
- Selector-mismatch Service (0 Endpoints): DNS **still resolves** (to the
  Service's own allocated ClusterIP -- Service DNS records exist
  independent of Endpoints), but curl on port 80 gets `Connection refused`
  immediately (kube-proxy has no backend to send it to). Confirms design
  (a): resolves-but-curl-fails.
  and I re-verified an explicit wrong-`targetPort` Service (Endpoints
  populated, but at the wrong port) also gets a fast `Connection refused`
  -- confirms design (b).
- Headless Service (`clusterIP: None`), 2 ready endpoints: DNS resolves
  straight to a **pod IP** (not a stable VIP -- `getaddrinfo` even returned
  both pod IPs, `gethostbyname` picked one). Curling that resolved address
  on port 80 (the Service's declared port) got `Connection refused`,
  because the pod's container only listens on 8080 and headless Services
  get no kube-proxy port translation at all. Confirms design (c) fails
  cleanly with the *same generic probe logic* as (a)/(b) -- no special-case
  code needed in the probe script.

This let me collapse all three defects onto one simple, generic probe
script (resolve FQDN, GET `http://<fqdn>:80/`, expect 200) instead of
needing bespoke per-defect assertions inside the probe. The Services'
public contract (`port: 80`) is fixed and never something the learner
needs to change -- only `selector` / `targetPort` / the presence of
`clusterIP: None` differ per defect, which also blocks a cheap dodge where
a learner just changes the Service's `port` field to dodge a targetPort
fix instead of correcting `targetPort` itself.

Cleaned up `zz-verify` fully (`kubectl delete namespace zz-verify`) before
writing any task files.

## Probe-job approach

`tests/validate.py` builds a `batch/v1` Job manifest inline (Python
f-string, applied via `kubectl apply -f -` with stdin) rather than shipping
it under `given/`, since it's the validator's own instrument, not
learner-facing content. Image: `sandbox20-app:1.0` (already built +
`kind load`ed per module contract; has python3 stdlib, no extra image
verification/loading needed). `command: ["python3", "-c"]` with the script
as a YAML block-scalar `args` entry (built via `textwrap.indent`, 14
spaces to match the manifest's nesting).

Script: loops over the 3 target FQDNs
(`catalog.t12.svc.cluster.local` etc.), each with internal retry loops
(`socket.gethostbyname`, up to 15x 1s; `urllib.request.urlopen` timeout=3s,
up to 5x with 1s backoff between attempts) to absorb DNS/rollout settling
time without a long fixed sleep. Prints `<label>: RESOLVED=<ip>` /
`<label>: STATUS=<code>` lines per target and exits 0 only if every target
resolved and returned exactly `200`.

`backoffLimit: 0` + `restartPolicy: Never` -- a single pod attempt, since
retries are handled inside the script itself; `activeDeadlineSeconds: 120`
as a safety net. Validator waits (`wait_until`, 150s budget) for the Job's
`status.conditions` to show `Complete: True` or `Failed: True`, then reads
`kubectl logs job/<name>` for diagnostics and `status.succeeded >= 1` for
the pass/fail signal.

Run twice with different Job names (`dns-probe-seed` against the
seeded-but-unfixed state, expected to fail; `dns-probe` after fixes,
required to succeed) -- confirmed non-vacuous per the module's repo-wide
rule, not just asserted via static field checks.

## Fix files / immutability gotcha

`catalog-peer`'s fix requires flipping `spec.clusterIP` from `None` to an
allocated address, which Kubernetes rejects as an immutable-field patch.
`_apply_fixes()` in the validator deletes all three Services
(`catalog`, `catalog-batch`, `catalog-peer`) before applying any of the
three `src/*-fix.yaml` files, uniformly (not just for `catalog-peer`), to
keep the apply step simple and to model "delete and recreate" as the
correct real-world move here. This is called out explicitly in
`catalog-peer-fix.yaml`'s comment block, hint-2, and hint-3, and in the
README's completion-criteria section, so it isn't a hidden trap.

## Stock-fail verification

Ran `uv run python tests/validate.py` against the stock (unfilled TODO)
stubs:

```
NOT PASSED: D:\...\12-services-and-dns-debugging\src\catalog-fix.yaml still looks like the unfilled TODO stub
EXIT=1
```

Single line, no traceback, exit 1, as required. (The stub check runs
before any cluster interaction, so this also confirms it fails fast.)

## Reference-pass verification

sha256 of the three stubs recorded before editing:

```
ffab2881a5058cdcbcbbd961ba5a90d27a91b43afc988b492c42dae425ab6601 *src/catalog-fix.yaml
03338d67994f7cd0152a086e0a0f81e01d20f40b00eb0068bbef722a4127fb20 *src/catalog-batch-fix.yaml
090dcc1930eac699e8eded2e8992dcd9fbe1e640f6c5c7439d3f4b955e8a1fc1 *src/catalog-peer-fix.yaml
```

Wrote throwaway correct fixes in place (matching the "Required shape"
comment blocks exactly: corrected selector, corrected targetPort:8080, and
a clusterIP-less Service respectively). Ran the validator:

```
PASSED: catalog (selector), catalog-batch (targetPort) and catalog-peer (headless) all fixed -- probe Job resolved and curled all three through their Service DNS names
EXIT=0
```

Passed on the first attempt -- no iteration needed. Reverted all three
files to the stock stub content and re-checked sha256: all three matched
the recorded values exactly (byte-identical revert confirmed). Re-ran the
validator against the reverted stock stubs: same single `NOT PASSED` line
as before, exit 1.

No reference solution was committed anywhere -- the throwaway fixes only
ever existed on disk transiently during this verification pass and were
overwritten back to the TODO stub before finishing.

## Cleanup

Namespace `t12` deleted (best-effort, non-blocking, via `delete_ns(...,
wait=False)`) at the end of every validator run, per the shared `finally`
block; confirmed fully gone (`kubectl get ns` shows no `t12`) after the
final stock re-run. No node taints/labels or cluster-global installs
touched by this task.

## Caveats / things a future editor of this task should know

- The `catalog-peer` "headless misuse" direction is the reverse of
  design.md's own one-line example phrasing (which reads as
  ClusterIP-should-have-stayed-headless -- actually re-reading it, the
  example says "client expects a stable VIP", i.e. ClusterIP was wrongly
  replaced by headless, which is exactly what I built; no actual
  contradiction, just flagging that I first considered the opposite
  direction and rejected it because it doesn't produce a deterministic
  curl failure under a healthy backend -- see the live-verification section
  above for why).
- The probe's use of a fixed `port: 80` for all three targets, checked
  against the Service's own declared `port` rather than a
  learner-adjustable value, is deliberate: it keeps the probe script
  static (no dynamic templating from `kubectl get svc` needed) and closes
  off a shortcut where a learner "fixes" `catalog-batch` by moving the
  Service's public `port` to 9090 instead of correcting `targetPort`.
