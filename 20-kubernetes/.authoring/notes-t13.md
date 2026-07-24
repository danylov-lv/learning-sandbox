# Task 13 authoring notes (ingress)

## ingress-nginx version pin

Pinned to **`controller-v1.12.1`**, not the newest v1.13.x/v1.15.x line.

`deploy/static/provider/kind/deploy.yaml` at `controller-v1.13.0` (and
presumably later in that line -- not checked further) **dropped the
`nodeSelector: {ingress-ready: "true"}`** on the controller Deployment that
every earlier release had (verified present at v1.9.6, v1.11.3, v1.12.1;
absent at v1.13.0). Without it, the controller's `nodeSelector` is just
`kubernetes.io/os: linux` plus a toleration for the control-plane taint --
it's *permitted* to land on the control-plane node but nothing *forces* it
there, and on this 3-node cluster it scheduled onto `sandbox20-worker2`
instead. `hostPort: 80/443` on a pod that isn't on the node kind maps
80->8320/443->9320 onto is silently useless: the port binds on the wrong
node's container, `127.0.0.1:8320` connects (kind's Docker port mapping to
the control-plane container succeeds) but nothing is listening there, so
every request gets an empty reply / connection with no response (`curl`:
"Empty reply from server", exit 52). No error anywhere -- this is a
schedule-time silent failure, not a crash, and it's the single biggest
gotcha in this task.

`v1.12.1` still has the `ingress-ready` nodeSelector and is confirmed in
ingress-nginx's own compatibility matrix to support Kubernetes 1.28-1.32,
which covers this cluster's `v1.32.2`. Confirmed live: after switching to
v1.12.1 the controller pod lands on `sandbox20-control-plane` every time
(checked across two separate installs), and `curl -H "Host: ..."
http://127.0.0.1:8320/` gets a real response (404 from the default backend
with no Ingress yet, 2xx from the backend app once the learner's Ingress is
applied).

If a future task author bumps this pin, **re-verify the nodeSelector is
still `ingress-ready: "true"` in the kind-provider manifest** before
trusting it, not just that the controller becomes Ready -- Ready-but-on-
the-wrong-node is a passing rollout status with a completely broken host
port.

## Install approach

`scripts/install.sh` just `kubectl apply -f` the official
`deploy/static/provider/kind/deploy.yaml` at the pinned tag (no kustomize,
no patching by hand -- the kind-provider variant already has the
nodeSelector + hostPort 80/443 + `--publish-status-address=localhost` this
task's topology needs) and waits on `rollout status
deployment/ingress-nginx-controller`.

Deliberately **does not** `kubectl wait --for=condition=complete` on the
`ingress-nginx-admission-create`/`ingress-nginx-admission-patch` Jobs --
both ship with `ttlSecondsAfterFinished: 0`, so they can (and did, in
testing) finish and get garbage-collected before a `wait` on them ever
observes "complete", producing a spurious `NotFound` error on a perfectly
successful install. Waiting on the controller Deployment rollout is
race-free and is what actually matters for reachability.

`kubectl apply` + `rollout status` is naturally idempotent/re-runnable;
verified by running `install.sh` twice back to back -- second run showed
`unchanged`/`configured` on every object, no pod restart, controller stayed
on the control-plane node throughout.

`scripts/uninstall.sh` is `kubectl delete -f` the same manifest URL,
`--ignore-not-found`.

## Host/URL contract (validator + README, must stay in sync)

- URL: `http://127.0.0.1:8320/` (the kind config's control-plane
  `extraPortMappings`, container port 80 -> host port 8320).
- Header: `Host: app.sandbox20.test`.
- Ingress object: `metadata.name: app`, `spec.ingressClassName: nginx`,
  one rule for that host, path `/` (`pathType: Prefix`) -> Service
  `backend` port `80`.
- Given backend: `given/backend.yaml`, Deployment `backend` (2 replicas,
  `sandbox20-app:1.0`) + Service `backend` (port 80 -> targetPort 8080),
  applied by the validator into namespace `t13` -- not learner-editable.
- Anti-cheat: validator also curls with a *wrong* Host header
  (`not-this-app.sandbox20.test`) and asserts it does **not** reach the
  app (ingress-nginx's own default-backend 404 instead) -- catches an
  Ingress with no host filter (or `host: ""`) that would pass a naive
  "does curl return 2xx" check without actually gating on Host.

## Stock-fail verification

Unfilled `src/ingress.yaml` stub (pure `# TODO(you)` comments, no YAML
document) against `kubectl apply -f`:

```
NOT PASSED: kubectl apply -f src/ingress.yaml failed: error: no objects passed to apply
```

Single line, exit 1, no traceback. Confirmed by running
`uv run python 13-ingress/tests/validate.py` from the module root with the
stub in place, both before and after the reference-pass test below (i.e.
after reverting).

## Reference-pass verification

Wrote a correct Ingress in place (`ingressClassName: nginx`, host
`app.sandbox20.test`, path `/` -> service `backend` port `80`), ran the
validator:

```
PASSED: Ingress 'app' routes Host 'app.sandbox20.test' -> Service backend:80, verified via a real curl through http://127.0.0.1:8320/
```

This is a genuine end-to-end curl through the kind host-port mapping into
the real ingress-nginx controller into the real backend Deployment/Service
-- not a port-forward, not a mock.

`sha256sum` of `src/ingress.yaml` recorded before writing the reference
Ingress and re-checked identical after reverting:
`20b44d93e9ed890098735c67fec0d9b342390170fdd7aa989426f9d0af9dc853`. Ran the
validator a third time after reverting to reconfirm the stock-fail line
above still reproduces. No reference solution was committed anywhere
(hints, tests, or `.authoring/`) -- the file on disk right now is the
original TODO stub.

## Cluster state left behind

- Namespace `t13`: deleted (validator's `finally` runs `delete_ns` on both
  the pass and fail paths; confirmed gone after the last run).
- ingress-nginx: **left installed** (task 13 owns it -- confirmed
  `deployment/ingress-nginx-controller` in ns `ingress-nginx` still
  `1/1` Ready and `ingressclass/nginx` still present after all testing).

## Other gotchas worth flagging

- `kubectl explain ingress.spec.rules.http.paths.backend.service.port`
  takes either `number` (int) or `name` -- the given Service doesn't name
  its port, so learners must use `number: 80`, not `name:`.
- `pathType` is mandatory in `networking.k8s.io/v1` (unlike the deprecated
  `extensions/v1beta1` API); a stub that's "almost right" but omits it
  fails Kubernetes' own API validation with a clear server-side message,
  which surfaces cleanly through the validator's existing
  `kubectl apply` failure path -- no special-casing needed on the
  validator side for that failure mode.
