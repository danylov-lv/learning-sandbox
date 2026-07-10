# Hint 3

Shape of the finished chart, in prose — the YAML is yours to write:

- `templates/cronjob.yaml`: a CronJob with your schedule from values;
  `concurrencyPolicy: Forbid` (two overlapping loads of the same day is
  exactly the double-write your capstone spent CP1 preventing);
  a modest `backoffLimit`; the pod runs your loader image with the
  target day derived at runtime (yesterday, or an env override) and the
  warehouse DSN assembled from values + the password Secret.
- `templates/deployment.yaml`: one replica of the monitor image (same
  image as the loader with a different command, or its own — either is
  defensible), the measured `resources` block from values, and if your
  monitor is the HTTP-server shape, a liveness/readiness probe against
  its endpoint. Labels: a small fixed set (e.g. app name + component)
  applied to the Deployment's pod template.
- `templates/pdb.yaml`: `policy/v1` PodDisruptionBudget whose
  `spec.selector.matchLabels` is exactly the monitor pod's labels and
  `minAvailable: 1` (from values). Yes, a PDB on a 1-replica Deployment
  is mostly a statement of intent — it blocks voluntary eviction rather
  than guaranteeing availability; that nuance belongs in your NOTES.md.
- `templates/secret.yaml`: the warehouse password, base64'd by the
  `b64enc` template function from a value (fine for a sandbox; note in
  NOTES.md what you'd do instead in production).

Deriving resources from measurement, concretely: run the monitor for a
few minutes of real check cycles; take steady-state rss and add
headroom (~50-100%) for the memory request, set the memory limit at or
modestly above the request (memory is incompressible — a limit far above
the request just moves the OOM surprise later); take the observed cpu
peak and set the request near typical usage with the limit at or above
peak (cpu is compressible — throttling, not death). Then write the raw
observed numbers as comments next to the values they justify. The
validator's copy-paste check is a warning, not a wall: if your honest
measurement lands on a default-looking number, the comment is what makes
it defensible.
