# 01. Row grain, joins, and aggregation

A dispatch manager wants a report for every warehouse, including warehouses
with no shipments. For each warehouse, show how many shipments it dispatched,
how many had at least one accepted scan, and the total weight dispatched.
A scanner can record several attempts for a shipment, so the report needs a
way to count each shipment and its weight once.

By the end of this chapter, you should be able to state what each row in a
query represents, predict how a join changes that grain, and check that the
report accounts for the intended set of rows.

## Row grain and join cardinality

The **grain** describes what one row represents. The **key** is the column or
combination of columns that identifies that row at the stated grain. In this
example, one shipment row represents one dispatched parcel and is identified
by `shipment_id`. One scan row represents one scan attempt and is identified
by `scan_id`. The requested report has one row per warehouse, keyed by
`warehouse_id`. A shipment may have several scans, so `shipment_id` identifies
a shipment in both tables and can repeat in the scan table.

Start PostgreSQL using the [module setup](../README.md#setup). From the module
directory, open a single session with `docker compose exec postgres psql -U sandbox -d sandbox`.
Run the examples in that session, starting with this fixture. They use temporary
tables and work without the module seed data.

```sql
BEGIN;

CREATE TEMP TABLE warehouses (
    warehouse_id integer PRIMARY KEY,
    warehouse_name text NOT NULL
);

CREATE TEMP TABLE shipments (
    shipment_id integer PRIMARY KEY,
    warehouse_id integer NOT NULL REFERENCES warehouses (warehouse_id),
    weight_g integer NOT NULL
);

CREATE TEMP TABLE scans (
    scan_id integer PRIMARY KEY,
    shipment_id integer NOT NULL REFERENCES shipments (shipment_id),
    status text NOT NULL
);

INSERT INTO warehouses VALUES
    (1, 'North'), (2, 'South'), (3, 'West');

INSERT INTO shipments VALUES
    (101, 1, 1200), (102, 1, 1200), (103, 2, 800);

INSERT INTO scans VALUES
    (1, 101, 'accepted'), (2, 101, 'accepted'), (3, 102, 'rejected');
```

For each join, ask how many right-hand rows can match each left-hand row.
With zero matches, an inner join drops the left row and a left join emits
one row with `NULL` in the right-hand columns. With one match, either join
emits one row. With several matches, both emit one row per match. If the join
key repeats on both sides, the output contains all matching pairs for that
key. [PostgreSQL 16 joined tables](https://www.postgresql.org/docs/16/queries-table-expressions.html#QUERIES-JOIN)

Joining a shipment to its warehouse by `warehouse_id` yields exactly one match
because the referenced key is unique and the non-null foreign key guarantees
that the warehouse exists. In the other direction, one warehouse can match
many shipments. Check constraints on the columns in the actual join predicate.
A key such as `(warehouse_id, shipment_id)` would guarantee uniqueness for the
pair and would still allow several matches on `warehouse_id` alone.
[PostgreSQL 16 primary and foreign keys](https://www.postgresql.org/docs/16/ddl-constraints.html#DDL-CONSTRAINTS-PRIMARY-KEYS)

An inner join from shipments to scans shows what happens when the right-hand
key can repeat and some shipments have no match.

```sql
SELECT s.shipment_id, s.weight_g, sc.scan_id, sc.status
FROM shipments AS s
JOIN scans AS sc ON sc.shipment_id = s.shipment_id
ORDER BY s.shipment_id, sc.scan_id;
```

| shipment_id | weight_g | scan_id | status |
| --- | ---: | ---: | --- |
| 101 | 1200 | 1 | accepted |
| 101 | 1200 | 2 | accepted |
| 102 | 1200 | 3 | rejected |

The input and the join result both have three rows. Shipment 101 appears twice
and shipment 103 disappears. The output weights add up to 3,600 g. The shipment
table sums to 3,200 g. A left join would bring back shipment 103
with a null scan ID, and shipment 101 would still occur twice.

To retain all shipments while joining only accepted scans, put
`sc.status = 'accepted'` in the left join's `ON` condition. The join then
emits null scan columns for both shipments 102 and 103. Applying that condition
in `WHERE` after joining on shipment ID keeps only the two accepted rows for
shipment 101. `WHERE` keeps rows whose predicate evaluates to true, so it
discards rows with a rejected or null status here.
[PostgreSQL 16 table expressions](https://www.postgresql.org/docs/16/queries-table-expressions.html#QUERIES-WHERE)

## Counting and conditional aggregates

`GROUP BY warehouse_id` produces a row for each warehouse ID present in
its input. Each aggregate operates on the rows in that group. A `WHERE`
clause changes the input population for every aggregate. Use `FILTER`
to restrict input to one aggregate and `HAVING` to keep or discard groups
after aggregation. [PostgreSQL 16 grouping and HAVING](https://www.postgresql.org/docs/16/queries-table-expressions.html#QUERIES-GROUP)
[PostgreSQL 16 aggregate expressions](https://www.postgresql.org/docs/16/sql-expressions.html#SYNTAX-AGGREGATES)

Start with the warehouses so West appears even though it has no shipments.
The following query compares several ways to count rows after both left joins.

```sql
SELECT w.warehouse_id,
       COUNT(*) AS joined_rows,
       COUNT(s.shipment_id) AS shipment_occurrences,
       COUNT(sc.scan_id) AS scan_count,
       COUNT(DISTINCT s.shipment_id) AS distinct_shipments,
       COUNT(*) FILTER (WHERE sc.status = 'accepted') AS accepted_scans
FROM warehouses AS w
LEFT JOIN shipments AS s ON s.warehouse_id = w.warehouse_id
LEFT JOIN scans AS sc ON sc.shipment_id = s.shipment_id
GROUP BY w.warehouse_id
ORDER BY w.warehouse_id;
```

| warehouse_id | joined_rows | shipment_occurrences | scan_count | distinct_shipments | accepted_scans |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 3 | 3 | 3 | 2 | 2 |
| 2 | 1 | 1 | 0 | 1 | 0 |
| 3 | 1 | 0 | 0 | 0 | 0 |

- `COUNT(*)` includes the row for West with null shipment and scan columns.
- `COUNT(column)` counts non-null values, including repeated values. Count a
  non-null key from the optional side of a left join to count its matches.
  If a later join repeats those matches, the count includes those repeats.
- `COUNT(DISTINCT column)` counts different non-null values within the group.
  For a composite key with non-null fields, PostgreSQL accepts a row expression
  such as `COUNT(DISTINCT (shipment_id, status))`. On `scans` this counts two
  different shipment/status pairs across three scan attempts.
- `COUNT(*) FILTER (WHERE ...)` counts input rows that meet its condition.
  Here two scans were accepted, both for the same shipment. On an empty
  filtered input, `COUNT` returns zero and `SUM` and `AVG` return `NULL`.
  [PostgreSQL 16 aggregate functions](https://www.postgresql.org/docs/16/functions-aggregate.html)

After these joins, `COUNT(DISTINCT s.shipment_id)` gives the correct
shipment count. `SUM(s.weight_g)` still counts shipment 101 twice.
`SUM(DISTINCT s.weight_g)` would count North's 1,200 g value only once, even
though it belongs to two different shipments. When several measures belong
at shipment grain, reduce scans to one row per shipment before attaching
them. That gives each shipment one contribution to the warehouse totals.

## Checking query stages

Use common table expressions (CTEs) to name the stages within one statement.
Define the key and population for each stage before combining them.
[PostgreSQL 16 SELECT in WITH](https://www.postgresql.org/docs/16/queries-with.html#QUERIES-WITH-SELECT)

| Stage | One row per | Population |
| --- | --- | --- |
| `scan_counts` | `shipment_id` | Shipments with at least one scan |
| `shipment_facts` | `shipment_id` | All shipments |
| `warehouse_summary` | `warehouse_id` | Warehouses with at least one shipment |
| Final report | `warehouse_id` | All warehouses |

```sql
WITH scan_counts AS (
    SELECT shipment_id,
           COUNT(*) FILTER (WHERE status = 'accepted') AS accepted_scan_count
    FROM scans
    GROUP BY shipment_id
),
shipment_facts AS (
    SELECT s.shipment_id, s.warehouse_id, s.weight_g,
           COALESCE(sc.accepted_scan_count, 0) AS accepted_scan_count
    FROM shipments AS s
    LEFT JOIN scan_counts AS sc ON sc.shipment_id = s.shipment_id
),
warehouse_summary AS (
    SELECT warehouse_id,
           COUNT(*) AS shipment_count,
           COUNT(*) FILTER (WHERE accepted_scan_count > 0) AS accepted_shipments,
           SUM(weight_g) AS total_weight_g
    FROM shipment_facts
    GROUP BY warehouse_id
)
SELECT w.warehouse_id, w.warehouse_name,
       COALESCE(ws.shipment_count, 0) AS shipment_count,
       COALESCE(ws.accepted_shipments, 0) AS accepted_shipments,
       COALESCE(ws.total_weight_g, 0) AS total_weight_g
FROM warehouses AS w
LEFT JOIN warehouse_summary AS ws ON ws.warehouse_id = w.warehouse_id
ORDER BY w.warehouse_id;
```

At shipment grain, shipment 101 carries two accepted scans and contributes
one accepted shipment. Shipment 102 has a scan count row with zero accepted
scans. Shipment 103 has no scan count row, so `COALESCE` supplies zero.
At warehouse grain, West has no summary row. Zero is appropriate for its
counts and total weight because it dispatched nothing.

| warehouse_id | warehouse_name | shipment_count | accepted_shipments | total_weight_g |
| --- | --- | ---: | ---: | ---: |
| 1 | North | 2 | 1 | 2400 |
| 2 | South | 1 | 0 | 800 |
| 3 | West | 0 | 0 | 0 |

To inspect or check a stage, reuse the `WITH` block above and replace the final
`SELECT` with one of the queries below. First inspect the rows around the join.

```sql
SELECT shipment_id, warehouse_id, weight_g, accepted_scan_count
FROM shipment_facts
ORDER BY shipment_id;
```

| shipment_id | warehouse_id | weight_g | accepted_scan_count |
| --- | --- | ---: | ---: |
| 101 | 1 | 1200 | 2 |
| 102 | 1 | 1200 | 0 |
| 103 | 2 | 800 | 0 |

Check the expected key for duplicates and nulls. For a composite key, group by
all its columns and check each required component for nulls.

```sql
SELECT shipment_id, COUNT(*) AS rows_per_key
FROM shipment_facts
GROUP BY shipment_id
HAVING COUNT(*) > 1 OR shipment_id IS NULL;
```

Check coverage by comparing the expected and actual keys. Use the relevant
filtered input as the expected population when the report has an eligibility
rule.

```sql
SELECT s.shipment_id AS input_key, f.shipment_id AS stage_key
FROM shipments AS s
FULL JOIN shipment_facts AS f ON f.shipment_id = s.shipment_id
WHERE s.shipment_id IS NULL OR f.shipment_id IS NULL;
```

Both checks should return zero rows here. In the earlier inner join to raw
scans, the two checks would expose the duplicated key 101 and the missing
key 103 even though the row totals agreed.

Reconcile measures that should carry through unchanged. Each shipment
belongs to exactly one warehouse, so the warehouse counts and weights can
be summed and compared with the shipment input.

```sql
SELECT 'shipments' AS stage, COUNT(*) AS shipment_count,
       SUM(weight_g) AS total_weight_g
FROM shipments
UNION ALL
SELECT 'warehouse_summary', SUM(shipment_count), SUM(total_weight_g)
FROM warehouse_summary
ORDER BY stage;
```

| stage | shipment_count | total_weight_g |
| --- | ---: | ---: |
| shipments | 3 | 3200 |
| warehouse_summary | 3 | 3200 |

Matching totals check that the measures reconcile across stages. Use them
alongside the key checks and inspect representative rows to verify which
group each entity contributes to.

### Self-check

1. Suppose a fourth scan arrives, also accepted and attached to shipment 101.
   Which North counts change in the raw join query? Which report measures
   change after pre-aggregation?
2. Suppose West dispatches one 500 g shipment without scans. What should
   West's three report measures become?

<details>
<summary>Check your reasoning</summary>

1. North's joined rows, shipment occurrences, scan count, and accepted scans
   each increase by one. The distinct shipment count stays at two. The final
   report still shows two shipments, one accepted shipment, and 2,400 g.
2. West shows one shipment, zero accepted shipments, and 500 g.

</details>

When you finish, roll back the fixture or close the session.

```sql
ROLLBACK;
```

[Back to the lecture index](../Lectures.md)
