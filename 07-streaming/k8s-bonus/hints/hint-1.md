# Hint 1

The two things that eat the evening if you discover them late — same
category as module 06's, different specifics:

1. **Network path, twice over.** This consumer needs to reach both the
   broker (redpanda, host port `19092` by default) and the warehouse
   Postgres from inside a pod running in kind. Settle both reachability
   questions with a throwaway pod (`nc -zv` for the broker,
   `pg_isready` for Postgres) before writing a single template.

2. **Image path.** Same as module 06: kind nodes don't see your host's
   docker image cache. Decide how the image gets in
   (`kind load docker-image`) before the Deployment template references
   it.

For the chart itself, this bonus adds two kinds you haven't templated
before in this repo: a HorizontalPodAutoscaler (`autoscaling/v2`) and a
PodDisruptionBudget targeting a Deployment with more than one replica.
Start from the API reference for each, not from a generated scaffold —
the HPA's `scaleTargetRef` and the PDB's `selector` both have to agree,
byte for byte, with names/labels the Deployment actually uses, or they
silently target nothing.
