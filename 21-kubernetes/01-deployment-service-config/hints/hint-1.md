# Hint 1

Four objects, but they only have two real dependencies between them: the
Deployment reads from the ConfigMap and the Secret (by name and key), and
the Service finds the Deployment's pods (by label selector). Write them in
this order so each one's inputs already exist when you need to reference
them: ConfigMap, Secret, Deployment, Service.

Each stub's comment block is close to the full shape already — the actual
work is filling in names, labels, and the env `valueFrom` blocks
correctly, not inventing structure from nothing. Look up the official
Kubernetes API reference for each `kind` if a field name is unfamiliar
rather than guessing.

Two traps worth knowing about before you start rather than after:

- The image `sandbox20-app:1.0` was built locally and loaded straight into
  kind's containerd — there is no registry backing it. The default
  `imagePullPolicy` in Kubernetes is `Always` when the tag isn't `latest`...
  actually check that claim yourself against the docs rather than trusting
  this sentence, but either way: think about what happens if kubelet tries
  to pull an image that exists nowhere reachable, and set the field
  explicitly rather than relying on a default you're not sure of.
- `REQUIRED_ENV` isn't decoration — the app in this image actually checks
  it at startup and exits if any listed var is missing. If your pods crash
  loop, that's usually telling you something about your env block, not
  about the platform.
