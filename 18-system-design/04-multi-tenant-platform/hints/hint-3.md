A concrete way to implement the progressive-filling loop described in the
README, without giving away what it produces for this workload:

Keep three pieces of running state: a set of tenant ids still "in play"
(call it `active`, starting as every tenant), a single number for capacity
not yet handed out (`remaining`, starting at usable capacity), and a dict
for the final answer (`allocation`, starting empty).

Each pass through the loop:

1. Add up the weights of everyone still in `active`.
2. Give each tenant in `active` a *tentative* share: their weight divided
   by that sum, times `remaining`. This is what they'd get if the
   capacity left over were split among only the tenants still in play.
3. Look at which of those tentative shares are already enough to cover
   that tenant's actual demand. If none are, you've hit the fixed point:
   nobody left in `active` can be fully satisfied, so everyone remaining
   gets locked in at their tentative share (that's their final
   allocation), and you're done.
4. If some tentative shares do cover their tenant's demand, those tenants
   are done -- lock their allocation in at exactly their demand (not their
   tentative share, which would overpay them), subtract that demand from
   `remaining`, and drop them out of `active`.
5. Go back to step 1 with the shrunk `active` set and the shrunk
   `remaining`. The tenants still in play get a fresh, larger tentative
   share next pass, because the capacity the just-satisfied tenants didn't
   fully use is now being split among fewer people.

This has to terminate: every pass either finishes the whole thing (step 3)
or removes at least one tenant from `active` (step 4), and `active` starts
finite, so you can't loop forever. A `while active:` loop with an internal
`if`/`else` matching steps 3 and 4 is enough structure -- no recursion
needed.

For `max_tenants_at_current_capacity`, remember the answer is a *count*,
not a rate -- get the headroom (usable capacity minus what's currently
demanded) and the size of an "average" tenant, then think about which
Python built-in rounds a division down to a whole number rather than
truncating toward zero, and what the right answer is when headroom is
already zero or negative.
