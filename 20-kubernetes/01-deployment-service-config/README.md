# 01 — Deployment, Service, ConfigMap, Secret

## Backstory

The scraping worker that's been living in someone else's Helm chart needs
a bare-bones deployment for a new environment, and there's no chart for it
yet — just the container image and a list of what it needs at runtime.
You're writing the raw Kubernetes objects by hand: no Helm, no template,
no `kubectl create` shortcuts you forget the shape of later. Four files,
each with a job: a Deployment that runs the worker, a ConfigMap and a
Secret that feed it configuration without baking anything into the image,
and a Service that gives the pods a stable address.

The fixture app you're deploying (`app/app.py`, already built into image
`sandbox20-app:1.0` and loaded into the kind cluster) refuses to start if
any env var named in `REQUIRED_ENV` is missing — so getting the env wiring
wrong isn't a subtle bug, it's a crash loop you'll see immediately.

## What's given

`src/` contains four stub files: `configmap.yaml`, `secret.yaml`,
`deployment.yaml`, `service.yaml`. Each has a `# TODO(you): ...` comment
block describing what belongs in it and nothing else — no `apiVersion`,
no `kind`, no working object. `kubectl apply -f src/` against the stubs
applies nothing (or fails cleanly); that's expected until you fill them in.

## What's required

Write all four objects from scratch so that, applied together into a
namespace, they produce a running worker:

- **ConfigMap** — any name you choose, with at least one key whose value
  you control (a greeting string works fine). This key's value is what
  `CONFIG_GREETING` will read from.
- **Secret** — any name you choose, type `Opaque`, with a key holding a
  token value of your choice. This key's value is what `APP_SECRET_TOKEN`
  will read from.
- **Deployment**:
  - name `worker`, `2` replicas.
  - pod template labels (and Deployment `selector`) `app: worker`.
  - container image `sandbox20-app:1.0`, `imagePullPolicy: IfNotPresent`.
    Read that policy value twice before you move on — this image was
    built locally and `kind load docker-image`d straight into the
    cluster's containerd; it does not exist in any registry. Get the pull
    policy wrong and you'll be staring at `ImagePullBackOff` for pods that
    otherwise would have started fine.
  - container port `8080`.
  - env vars on the container:
    - `CONFIG_GREETING` — sourced from your ConfigMap key via
      `configMapKeyRef` (not a literal value).
    - `APP_SECRET_TOKEN` — sourced from your Secret key via
      `secretKeyRef` (not a literal value).
    - `APP_POD_NAME` — sourced from the pod's own name via the downward
      API (`fieldRef`, `fieldPath: metadata.name`).
    - `REQUIRED_ENV` — literal value `CONFIG_GREETING,APP_SECRET_TOKEN`.
      This is what makes the app refuse to start (see `app/app.py`'s
      `check_required_env`) if you wire the two config sources wrong —
      treat a crash loop here as a signal to check your env block, not a
      surprise.
- **Service**:
  - name `worker`, type `ClusterIP` (the default — you can also state it
    explicitly).
  - selects the Deployment's pods (`app: worker`).
  - `port: 80` routing to `targetPort: 8080`.

## Completion criteria

From this task directory:

```bash
uv run python tests/validate.py
```

The validator applies everything in `src/` into namespace `t01` (created
fresh, deleted at the end whether you pass or fail), waits for the
Deployment to roll out, and checks:

- the Deployment reports 2 ready replicas within the rollout timeout;
- the Service has exactly 2 endpoints;
- port-forwarding to the Service, `GET /` returns `app_version: "1.0"`;
- `GET /env?name=CONFIG_GREETING` echoes a non-empty, non-placeholder
  value (i.e. you actually changed it from whatever the stub's TODO said);
- inspecting the running pod's spec (not the app's response): `CONFIG_GREETING`
  is wired via `configMapKeyRef`, `APP_SECRET_TOKEN` via `secretKeyRef`,
  and `APP_POD_NAME` via a downward-API `fieldRef` — a hardcoded literal
  value in any of those three slots fails validation even if the app
  happens to start;
- the container's `imagePullPolicy` is `IfNotPresent`;
- the Secret object exists and its `type` is `Opaque`.

## Estimated evenings

1

## Topics to read up on

- Deployment `spec.selector` vs. pod template `metadata.labels` — why they
  must match, and what happens (at apply time and at drift time) when they
  don't.
- `configMapKeyRef` / `secretKeyRef` under `env[].valueFrom` — the
  difference between wiring a single key this way vs. `envFrom` importing
  every key.
- the downward API: which pod/container fields are available via
  `fieldRef` inside `env[].valueFrom`, and which need `resourceFieldRef`
  or a mounted volume instead.
- `imagePullPolicy: Always` vs. `IfNotPresent` vs. `Never`, and why a
  cluster with no image registry configured needs one of them explicitly
  rather than relying on the Kubernetes default.
- Service `spec.selector` matching pod labels, and `port` vs.
  `targetPort` — what each one means from the client's side vs. the
  pod's side.
- Secret `type: Opaque` vs. the other built-in Secret types, and why a
  Secret in Kubernetes is base64-encoded rather than encrypted by default.
