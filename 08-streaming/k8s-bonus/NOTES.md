# NOTES

## Measurements — consumer resources

| observation | value |
|---|---|
| measurement tool (kubectl top / docker stats) |  |
| cpu, idle between poll cycles |  |
| cpu, peak while polling + writing |  |
| memory (rss), steady state |  |
| observation window |  |
| requests set (cpu / memory) |  |
| limits set (cpu / memory) |  |

## Cluster wiring

| item | choice |
|---|---|
| how the broker is reachable from kind |  |
| how the warehouse is reachable from kind |  |
| how the image got into the cluster |  |
| HPA bounds (min/max) and CPU target, and why |  |
| PDB guarantee (minAvailable / maxUnavailable) and why |  |

## Rebalance observation

| observation | value |
|---|---|
| replicas before scale |  |
| replicas after scale |  |
| partitions reassigned (from `rpk group describe` / console) |  |
| anything reprocessed across the rebalance boundary |  |

## What I learned

(fill in after completing the task)

## Gotchas

(fill in after completing the task)

## What I'd change before calling this production-grade

(fill in after completing the task)
