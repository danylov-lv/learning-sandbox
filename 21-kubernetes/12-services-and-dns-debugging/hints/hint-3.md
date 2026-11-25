# Hint 3

Concrete sequence, not paste-ready YAML -- you still have to look at your
own output and decide the actual values.

**catalog** (selector mismatch):

1. `kubectl -n t12 get pods --show-labels` -- note the real `app=...` label
   on `catalog-backend`'s pods.
2. `kubectl -n t12 get svc catalog -o yaml` -- compare `spec.selector`
   against what you just saw.
3. Write `src/catalog-fix.yaml` as a complete Service object with the
   corrected `selector`, keeping `port: 80` / `targetPort: 8080`.
4. `kubectl -n t12 apply -f src/catalog-fix.yaml`, then
   `kubectl -n t12 get endpoints catalog` -- it should now list two
   addresses.

**catalog-batch** (wrong targetPort):

1. `kubectl -n t12 get endpoints catalog-batch` -- note the port number
   next to the pod IPs.
2. `kubectl -n t12 get deploy catalog-backend -o jsonpath='{.spec.template.spec.containers[0].ports}'`
   -- note the real `containerPort`.
3. Write `src/catalog-batch-fix.yaml` as a complete Service object with
   `targetPort` corrected to match, keeping `port: 80` and the (already
   correct) selector.
4. `kubectl -n t12 apply -f src/catalog-batch-fix.yaml`, then
   `kubectl -n t12 get endpoints catalog-batch` to confirm the port
   changed.

**catalog-peer** (headless misuse):

1. `kubectl -n t12 get svc catalog-peer -o jsonpath='{.spec.clusterIP}'` --
   confirm it prints `None`.
2. Since `spec.clusterIP` is immutable on an existing Service, delete it
   first: `kubectl -n t12 delete svc catalog-peer`.
3. Write `src/catalog-peer-fix.yaml` as a complete Service object with the
   same selector/ports as before but **no `clusterIP` field at all** (let
   Kubernetes allocate one).
4. `kubectl -n t12 apply -f src/catalog-peer-fix.yaml`, then
   `kubectl -n t12 get svc catalog-peer -o jsonpath='{.spec.clusterIP}'` --
   it should now print a real IP.

To see the whole chain end to end for any of the three, run a throwaway
debug pod and check both the DNS answer and the HTTP response from inside
the cluster:

```bash
kubectl -n t12 run dnsprobe --image=sandbox20-app:1.0 --image-pull-policy=IfNotPresent --restart=Never --command -- sleep 300
kubectl -n t12 exec dnsprobe -- python3 -c "import socket; print(socket.gethostbyname('catalog-peer.t12.svc.cluster.local'))"
kubectl -n t12 exec dnsprobe -- python3 -c "import urllib.request; print(urllib.request.urlopen('http://catalog-peer.t12.svc.cluster.local:80/', timeout=3).status)"
kubectl -n t12 delete pod dnsprobe
```

Run `uv run python tests/validate.py` once all three are in place. It
re-seeds the namespace from scratch each time, so partial progress from a
manual `kubectl apply`/`delete` doesn't carry over between runs -- always
drive the fix through `src/*.yaml`, not ad hoc edits you made by hand while
debugging.
