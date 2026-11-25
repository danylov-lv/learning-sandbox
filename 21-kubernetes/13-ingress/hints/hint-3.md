# Hint 3

Rough shape, not paste-ready YAML:

```
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app
spec:
  ingressClassName: nginx
  rules:
    - host: app.sandbox20.test
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: backend
                port:
                  number: 80
```

That's the whole thing — one rule, one path, one backend. If
`uv run python tests/validate.py` still fails after this applies cleanly,
the usual next move is the exact `curl -H "Host: ..." http://127.0.0.1:8320/`
from hint 1 (does the same request the validator makes actually work by
hand?), then `kubectl --context kind-sandbox20 -n t13 describe ingress app`
(does ingress-nginx's own event log show it accepted the rule?).
