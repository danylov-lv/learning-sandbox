# Kupitron Database Audit

Copy this file to `REPORT.md` in this same directory and fill it in as you
work through the three checkpoints. Keep the section headings (`## 1.`
through `## 8.`) exactly as they are -- the checkpoint validators look for
them by number to confirm the report is complete. What you write under each
heading is entirely up to you; only completeness is machine-checked.

## 1. Inventory

Tables, row counts, index census, bloat snapshot. What does this database
actually look like today?

## 2. Workload Triage

One row per workload query. Fill in every `qcNN` row -- the checkpoint
validator requires a non-empty root-cause cell for each.

| query | baseline median (ms) | worst plan node | suspected root cause |
|-------|----------------------|------------------|-----------------------|
| qc01  |                      |                  |                       |
| qc02  |                      |                  |                       |
| qc03  |                      |                  |                       |
| qc04  |                      |                  |                       |
| qc05  |                      |                  |                       |
| qc06  |                      |                  |                       |
| qc07  |                      |                  |                       |
| qc08  |                      |                  |                       |

## 3. Root-Cause Map

For each defect family you found, which workload queries does it affect?
Group by cause, not by query -- this is the reverse index of section 2.

## 4. Fix Plan

Prioritized list of fixes. For each: what you'd do, why it's ranked where it
is, and what effect you expect (structural, timing, or both).

## 5. Applied Fixes

One row per workload query: what you actually did, and the before/after
median. Fill in every `qcNN` row.

| query | fix applied | before (ms) | after (ms) |
|-------|-------------|-------------|------------|
| qc01  |             |             |            |
| qc02  |             |             |            |
| qc03  |             |             |            |
| qc04  |             |             |            |
| qc05  |             |             |            |
| qc06  |             |             |            |
| qc07  |             |             |            |
| qc08  |             |             |            |

## 6. Hygiene

Vacuum/autovacuum state, statistics freshness, redundant indexes. What did
you find, and what did you do about it?

## 7. Type-Hygiene Findings

`orders.total_amount` / `payments.amount` as `numeric(30,10)`, `status`
columns as `varchar(10)`, `orders.user_id` (`bigint`) vs. `users.id`
(`int4`). Analysis only -- no migration required. What would you actually
recommend, and why (or why not)?

## 8. Remaining Risks / Next Steps

What did you deliberately not fix, and why? What would you flag for the next
person who inherits this database?
