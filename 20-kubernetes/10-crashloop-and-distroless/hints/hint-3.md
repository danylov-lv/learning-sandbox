# Hint 3

Concrete sequence, not paste-ready YAML -- you still have to look at your
own output and decide the actual values.

**ingest**:

1. `kubectl -n t10 logs deploy/ingest --previous` -- read the FATAL line, it
   names the exact missing var.
2. `kubectl -n t10 get configmap ingest-config -o yaml` -- see what's already
   there (`DB_URL`) so you can add a matching `QUEUE_URL` key alongside it,
   or decide to skip the ConfigMap and use a literal `value:` instead.
3. Write `src/ingest-fix.yaml` as a complete ConfigMap (if you touched it) +
   complete Deployment, re-listing every field the container already had
   (image, ports, the other env entries) plus your new one.
4. `kubectl apply -n t10 -f src/ingest-fix.yaml`, then
   `kubectl -n t10 rollout status deploy/ingest` -- it should complete
   instead of timing out on a crash loop.

**render**:

1. `kubectl -n t10 describe pod -l app=render` -- confirm the readiness
   probe is what's failing, note which port it's hitting.
2. `kubectl -n t10 debug -it render-debug-target --image=sandbox20-app:1.0
   --image-pull-policy=IfNotPresent --target=render -- sh` -- you're now in
   an ephemeral container sharing the target's network namespace. From
   here: `cat /proc/1/environ | tr '\0' '\n' | grep PORT` tells you what
   port the app was actually told to bind, and something like
   `python3 -c "import urllib.request;
   print(urllib.request.urlopen('http://localhost:<port>/readyz').read())"`
   (no `curl`/`wget` in this image, `python3` is) proves it's actually
   listening there while the probe's port isn't.
3. Decide your fix (adjust `containerPort`/`readinessProbe.port` to the
   real port, or set `PORT` back to what they already expect), write
   `src/render-fix.yaml` as a complete Deployment, keeping
   `image: sandbox20-app:distroless`.
4. `kubectl apply -n t10 -f src/render-fix.yaml`, then
   `kubectl -n t10 rollout status deploy/render` and
   `kubectl -n t10 port-forward svc/render 8080:80` +
   `curl localhost:8080/readyz` to confirm end to end.

Run `uv run python tests/validate.py` once both are in place. It re-seeds
the namespace from scratch each time, so partial progress from a manual
`kubectl apply` doesn't carry over between runs -- always drive the fix
through `src/*.yaml`, not ad hoc edits you made by hand while debugging.
