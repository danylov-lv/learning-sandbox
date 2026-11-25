# Hint 1

Start with `src/crd.yaml`, not the operator -- nothing else works until
`kubectl apply -f src/crd.yaml` succeeds. Get that clean first: apply it
and confirm with `kubectl --context kind-sandbox20 get crd
scrapejobs.sandbox20.dev` that it's `Established`. A CRD's OpenAPI schema
lives under `spec.versions[0].schema.openAPIV3Schema` -- it's easy to put
`spec.replicas`/`image`/`processMs` one level too shallow or too deep the
first time. Once the CRD is in, hand-write a tiny `ScrapeJob` YAML and
`kubectl apply` it too, before writing a single line of `operator.py` --
if that doesn't parse the way you expect, no amount of operator code will
fix it.

Only then move to `on_create`. Don't try to get update and delete working
in the same sitting -- CP1 only needs create, and kopf's `@kopf.on.create`
handler receives `spec`, `name`, `namespace`, and `logger` as keyword
arguments matching your function's parameter names (kopf inspects your
signature and only passes what you ask for -- you don't need to accept
every possible kwarg, but you do need `**kwargs` to swallow the rest kopf
always sends).

Two things worth knowing before you write your first Deployment manifest:

- `kubernetes.client.AppsV1Api()` needs SOME authenticated Kubernetes
  client configured before you call it. You get this for free here --
  kopf's own startup activity (`login_via_client`) configures the
  official `kubernetes` client library's default config as a side effect
  of kopf authenticating itself, so `client.AppsV1Api()` just works
  inside a handler without you calling `kubernetes.config.load_*` again.
  Don't add that call; it's redundant and can only get out of sync with
  what kopf already set up.
- Run `uv run python -m kopf run src/operator.py --namespace t22
  --verbose` by hand once, in one terminal, while you `kubectl apply`
  test CRs in another. Watching the real log output (or the stack trace
  when your handler blows up) is much faster feedback than round-tripping
  through the validator every time.
