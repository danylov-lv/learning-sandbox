# Hint 1

Run `scripts/install.sh` before you write anything — there's no point
iterating on `src/ingress.yaml` against a controller that isn't there yet.
The script prints the IngressClass name and the two host ports at the end;
`kubectl --context kind-sandbox20 get ingressclass` and `kubectl --context
kind-sandbox20 -n ingress-nginx get pods` are your two sanity checks if
something looks off.

The Ingress you write has exactly three things that matter: which
IngressClass implements it, which Host header it matches, and which
Service/port it sends matching requests to. Everything else in the spec is
structure around those three facts. If you're unsure of the shape, `kubectl
explain ingress.spec` (and `--recursive` for the full tree) is faster and
more reliable than guessing from memory.

Once ingress-nginx is installed and your Ingress is applied, you can sanity
check it yourself before running the validator:

```bash
curl -H "Host: app.sandbox20.test" http://127.0.0.1:8320/
```

If that hangs or connection-refuses, the controller itself isn't reachable
on 8320 (check the install). If it returns nginx's own 404 page, the
controller is up but your Ingress isn't matching the way you think it is
(wrong host, wrong ingressClassName, or the Ingress didn't apply cleanly).
