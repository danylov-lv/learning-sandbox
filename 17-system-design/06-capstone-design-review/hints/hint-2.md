On the capacity model: build the derived quantities as small internal
helper functions (or just local variables recomputed inline — either is
fine, this file is not graded on structure) rather than copy-pasting the
same expression into five public functions. `daily_new_rows`,
`daily_new_rows_effective`, `per_pod_capacity`,
`fetch_egress_bytes_per_month`, and `delivery_records_per_month` each feed
more than one required function. If you find yourself typing the same
five-line expression a third time, that is the signal to factor it out.

For the 10x functions specifically: build one small helper that takes a
workload dict and returns a NEW dict (do not mutate the input) with
`acquisition.total_tracked_urls` and `clients.tenant_count` scaled by
`ops.growth_multiplier_10x`, then call your regular `fleet_size` /
`storage_hot_bytes` / `storage_cold_bytes` / `total_monthly_cost` logic
against that derived dict. Do not write a separate parallel set of
formulas for the 10x case — that is exactly the kind of duplication that
drifts out of sync and fails the validator's perturbation checks.

On the ADRs: pick decisions you can genuinely argue both sides of, given
your own two years of scraping experience. If you cannot think of a
rejected alternative with a real trade-off, that is a sign the ADR topic
is not actually contested for you yet — read the "Context" prompt in the
template again and think about what a colleague with a different
background (e.g. someone from a data-warehouse team, or someone who has
only ever run managed cloud queues) would have argued for instead.
