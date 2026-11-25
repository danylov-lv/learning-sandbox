A concrete shape for `src/estimate.py` that avoids re-deriving the same
intermediate values in every function (the README's "Capacity model
contract" already has every formula pinned exactly — this hint is about
code structure, not arithmetic):

```python
def _derived(workload):
    """Compute every intermediate quantity the README's formulas name,
    once, and return them in a dict. Every public function below reads
    from this dict instead of recomputing things inline."""
    acq = workload["acquisition"]
    # daily_new_rows: sum over tiers, per the README's formula
    # expected_attempts_per_url: per the README's formula
    # daily_new_rows_effective = daily_new_rows * expected_attempts_per_url
    # per_pod_capacity: per the README's formula
    # fetch_egress_bytes_per_month, delivery_records_per_month,
    # delivery_egress_bytes_per_month: per the README's formulas
    return {...}  # one key per intermediate quantity above


def _grown(workload):
    """Return a NEW dict: total_tracked_urls and tenant_count each scaled
    by ops.growth_multiplier_10x, everything else unchanged. Use this
    inside fleet_size_at_10x and storage_and_cost_at_10x, calling back
    into the SAME logic fleet_size / storage_hot_bytes / etc. use — do
    not fork the formulas."""
    ...


def fleet_size(workload):
    d = _derived(workload)
    # ceil(...) using d["required_fetch_capacity_per_sec"] and
    # d["per_pod_capacity"] and workload["ops"]["target_utilization"]
    ...
```

For the document side: when answering the hostile-review `### Qn`
subsections, write each answer as (1) a specific claim about THIS design,
(2) the number or component name that grounds it, (3) what you would do
differently if you are wrong. An answer that could be pasted unchanged
into a different capstone's `DESIGN.md` is not grounded enough — the
validator rejects verbatim-question-only answers, but a generic answer
that happens to be long enough to pass is still a weak answer; the
grading you actually care about is whether it would survive a real
review panel.

For `REVIEW.md`: pick weaknesses you can point to a specific section or
number for — e.g. "my `Degradation ladder` section sheds tenant traffic
before it sheds internal batch analytics jobs, and I am not confident
that ordering survives contact with a real incident" is a real,
falsifiable weakness; "the design could be more scalable" is not.
