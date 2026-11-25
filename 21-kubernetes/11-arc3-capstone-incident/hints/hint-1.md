# Hint 1

You have five components in `t11`: `redis`, `pipeline-config` (a
ConfigMap, not a workload, but part of the graph), `api`, `worker`,
`producer`. Before you touch anything, build the full picture -- don't
fix the first red thing you see.

Start with `kubectl -n t11 get pods`. Something is very obviously wrong
with at least one Deployment there -- that's your paging symptom, the
thing that would actually wake someone up. But resist the urge to stop
there. A pod that's `Running`/`Ready` is not the same thing as a pod that
is *doing its job*. Check whether the pipeline is actually flowing data
end to end, not just whether every container is up.

`kubectl -n t11 logs deploy/<name> --previous` is the single most
important command here for the thing that's actually crashing --
`--previous` gets you the last attempt's log, not the current attempt
(which may not have logged anything useful yet). Read the exact line it
prints before it exits, don't paraphrase it in your head.

For the component that looks fine but isn't: it can't tell you what's
wrong through its own logs, because from where it's sitting, nothing *is*
wrong -- it's doing exactly what its configuration tells it to do. You'll
need to check the actual queue state directly (there's a redis pod in
this namespace; `kubectl exec` into it and ask it yourself what it thinks
the queue looks like) rather than trusting any one app's self-report.
