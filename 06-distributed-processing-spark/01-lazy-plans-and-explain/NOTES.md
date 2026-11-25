# NOTES

## Measurements

| checkpoint | job count |
|---|---|
| after source read |  |
| after transformations only |  |
| after action 1 |  |
| after action 2 |  |

| comparison | narrow plan | wide plan |
|---|---|---|
| contains `Exchange`? |  |  |

| comparison | JSONL scan | Parquet scan |
|---|---|---|
| `Batched` |  |  |
| `PushedFilters` non-empty |  |  |

| filter_probe | rows | price_sum |
|---|---|---|
| mine |  |  |
| ground truth | 13948 | 1414004.45 |

## Postgres EXPLAIN parallel

(fill in after completing the task — map specific Postgres EXPLAIN concepts to specific Spark plan nodes you saw: e.g. what plays the role of a seq scan vs an index scan; what plays the role of a hash join; what in Spark has no real Postgres equivalent and why)

## What I learned

(fill in after completing the task)

## Gotchas

(fill in after completing the task)

## Open questions

(fill in after completing the task)
