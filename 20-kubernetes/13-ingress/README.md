# 13 — Ingress

## Backstory

Every task so far has reached the fixture app through a Service — either
port-forwarded straight to your terminal, or hit from inside the cluster by
another pod. That's fine for a worker, but a real user-facing app needs a
stable URL a browser (or `curl`) can hit from outside the cluster, without
`kubectl port-forward` running in a side terminal, and ideally with more
than one app sharing the same IP and port by hostname. That's what an
Ingress controller is for: one thing listens on 80/443, and a set of
Ingress objects tell it which Host header + path goes to which Service.

This task has two parts. First, you install the ingress controller itself
— cluster-scoped, done once, and owned by this task directory for the rest
of the module. Second, you write the Ingress resource that actually routes
traffic to a backend that's already running.

## What's given

- `given/backend.yaml` — a Deployment (`backend`, 2 replicas, the fixture
  app on `sandbox20-app:1.0`) and a Service (`backend`, port 80 ->
  `targetPort: 8080`). The validator applies this into namespace `t13`
  itself; you don't need to touch it. It's there so you can see exactly
  what your Ingress needs to route to.
- `scripts/install.sh` — installs ingress-nginx into the cluster (pinned to
  `controller-v1.12.1`, using the official kind-provider manifest that
  already targets the `ingress-ready=true` control-plane node and binds
  host ports 80/443). Run this **once**, yourself, before anything else in
  this task:

  ```bash
  bash scripts/install.sh
  ```

  It's safe to re-run — everything it does is idempotent. Once installed,
  ingress-nginx stays installed for the rest of the module; later tasks
  assume it's already there. Don't run `scripts/uninstall.sh` unless you
  specifically want to tear it down and re-verify the install yourself.

- `src/ingress.yaml` — a `# TODO(you): ...` stub. This is the only file you
  write.

## What's required

Write an `Ingress` in `src/ingress.yaml`:

- `metadata.name: app`
- `spec.ingressClassName: nginx` (the IngressClass ingress-nginx registers
  itself as — check `kubectl get ingressclass` after installing to confirm
  the name).
- one rule with `host: app.sandbox20.test` routing path `/` (`pathType:
  Prefix`) to Service `backend`, port `80`.

**The exact contract the validator checks:** a request to
`http://127.0.0.1:8320/` with header `Host: app.sandbox20.test` must reach
the backend app (its `/` response, containing `"app_version"`, proves the
request actually got there — not just that *something* answered on
`8320`). `127.0.0.1:8320` is the host port `cluster/kind-config.yaml` maps
onto the ingress-ready control-plane node's container port 80 — this is
how a request from your machine ends up at the in-cluster ingress-nginx
controller without any port-forwarding. A request with a different Host
header must **not** reach it (ingress-nginx's default backend answers
instead) — your rule has to gate on Host, not catch every request that
shows up.

## Completion criteria

From this task directory (after `scripts/install.sh` has been run once,
either by you or already by a previous session):

```bash
uv run python tests/validate.py
```

The validator:

1. confirms ingress-nginx is installed and its controller has at least one
   ready replica (fails with a clear message pointing at
   `scripts/install.sh` if not);
2. seeds `given/backend.yaml` into a fresh namespace `t13` and waits for
   the Deployment to roll out;
3. applies `src/ingress.yaml` into `t13`;
4. inspects the resulting `Ingress` object's spec directly — `ingressClassName`,
   the `app.sandbox20.test` host rule, and the `backend`/`80` target must
   all be present and correct, not just "an Ingress named app exists";
5. curls `http://127.0.0.1:8320/` with `Host: app.sandbox20.test` and
   asserts a 2xx response containing `"app_version"` — and confirms a
   *different* Host header does **not** reach the backend.

Namespace `t13` is deleted at the end whether you pass or fail.
ingress-nginx is left installed either way — it's shared cluster
infrastructure for the rest of the module.

## Estimated evenings

1

## Topics to read up on

- Ingress vs. Service: why a Service alone (`ClusterIP`/`NodePort`/
  `LoadBalancer`) doesn't give you host-based or path-based routing across
  multiple backends on one IP, and what problem an Ingress *object* + an
  Ingress *controller* split solves that a Service can't.
- What an ingress controller actually is — it's not a built-in Kubernetes
  component; nothing routes Ingress traffic until something (ingress-nginx,
  here) is running, watching Ingress objects, and holding the port.
- `spec.ingressClassName` — how a cluster can run more than one ingress
  controller, and how an Ingress object picks which one implements it (vs.
  the older, now-deprecated `kubernetes.io/ingress.class` annotation).
- Host-based vs. path-based routing: what changes in the Ingress spec for
  each, and why a bare `path: /` with `pathType: Prefix` matches broadly
  compared to `Exact`.
- How kind maps a controller's host-networked/hostPort binding on one node
  out to your machine — re-read `cluster/kind-config.yaml`'s
  `extraPortMappings` and the `ingress-ready=true` node label, and look at
  what `deploy/static/provider/kind/deploy.yaml` (the manifest
  `scripts/install.sh` applies) actually patches onto the controller
  Deployment to make that binding happen.
- Why the validator sends a `Host` header explicitly with `curl -H`/
  `requests`' `headers=` instead of relying on DNS — nothing on your
  machine resolves `app.sandbox20.test` to anything, and that's fine;
  Ingress routing is decided by the `Host` header ingress-nginx reads out
  of the request, not by what name you looked up to get an IP.
