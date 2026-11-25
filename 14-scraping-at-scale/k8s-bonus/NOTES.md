# NOTES

## Measurements — spider worker resources

| observation | value |
|---|---|
| measurement tool (kubectl top / docker stats) |  |
| cpu, idle between crawl cycles |  |
| cpu, peak while crawling + parsing |  |
| memory (rss), steady state |  |
| observation window |  |
| requests set (cpu / memory) |  |
| limits set (cpu / memory) |  |

## Chart / cluster choices

| item | choice |
|---|---|
| pod label set (defined once, reused by Deployment/HPA/PDB) |  |
| HPA bounds (min/max) and CPU target, and why |  |
| why CPU and not queue depth (and what the real answer would be) |  |
| PDB guarantee (minAvailable / maxUnavailable) and why |  |
| liveness vs. readiness probe endpoints and why |  |
| how the target site is reachable from kind (if you did the live stretch) |  |
| how the image got into the cluster (if you did the live stretch) |  |

## Scaling observation (optional live stretch)

| observation | value |
|---|---|
| replicas before scale |  |
| replicas after scale |  |
| what happened to in-flight crawl work on scale-down |  |
| did the HPA move replicas on its own under load |  |

## What I learned

(fill in after completing the task)

## Gotchas

(fill in after completing the task)

## Open questions

(fill in after completing the task)
