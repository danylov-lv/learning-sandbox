For the capacity model, work through the functions in dependency order --
several of them build on an earlier one, and getting the order right
avoids re-deriving the same intermediate value with two slightly different
formulas by accident.

`total_demand_rps` and `overcommit_ratio` are one-liners once you've read
the "usable capacity" definition in the README (capacity times the target
utilization factor -- not raw platform capacity).

`fair_share_allocation` is the one worth sketching on paper before typing
any code. It is not "give everyone `weight / total_weight` of the total
capacity and stop" -- that plain proportional split is only correct when
every tenant's demand is at or above its proportional share. The moment
one tenant's demand is *below* what its weight would entitle it to, that
tenant is fully satisfied at its demand, not at its share, and the
capacity you didn't give it doesn't vanish -- it has to go somewhere. That
"somewhere" is the rest of the tenants, split among *them* by weight, and
the same question repeats: does everyone left over now want at least
their new, bigger share? If yes, stop. If not, repeat again. This is why
it is a loop, not a single division.

`unsatisfied_tenants`, `tenant_monthly_cost_usd`, and
`tenant_monthly_margin_usd` are all straightforward once
`fair_share_allocation` is correct, since they all read from its output --
notice the README says cost is attributed at the *allocated* rate, not the
demanded rate. `capacity_rps_for_slo` and `max_tenants_at_current_capacity`
don't depend on the fair-share loop at all -- they're direct algebra on
`total_demand_rps` and the usable-capacity definition.
