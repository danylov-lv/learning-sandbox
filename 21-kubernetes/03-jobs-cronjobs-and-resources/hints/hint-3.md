# Hint 3

Not paste-ready YAML — a field-by-field walk-through of the CronJob knobs
this task grades, so you can look each one up and decide the value
yourself.

**`schedule`** is standard five-field cron syntax:
`minute hour day-of-month month day-of-week`, each field either a
literal, a `*` (any), or more advanced forms (`*/5`, ranges, lists) you
won't need here. `* * * * *` — every field a wildcard — means "every
minute, every hour, every day." That's unusually aggressive for a real
production re-scrape schedule; it's this aggressive here purely so a
validator doesn't have to wait an hour to see the CronJob fire once.

**`concurrencyPolicy`** decides what happens if a scheduled tick arrives
while the *previous* run's Job is still active:
- `Allow` (the default) — start the new one anyway, both run at once.
- `Forbid` — skip this tick entirely, leave the running one alone.
- `Replace` — kill the currently-running Job's pods and start the new one.

For a re-scrape you don't want two overlapping runs hammering the same
target twice, but you also don't want to kill an in-progress run
partway through — that narrows it to one specific value among the three.

**`successfulJobsHistoryLimit` / `failedJobsHistoryLimit`** cap how many
completed Job objects (and their pods) the CronJob controller keeps
around after they finish, one counter for the ones that succeeded and a
separate one for the ones that didn't — old ones beyond the limit get
garbage collected. This is bookkeeping hygiene, not a live behavior you
can observe instantly: with a schedule this fast you'd need several
minutes of ticks actually accumulating history before pruning becomes
visible, which is why this task's own validator only checks that you
*set* the fields correctly, not that pruning has already happened.

**`startingDeadlineSeconds`** answers "if the scheduler couldn't start
this run at its scheduled time for some reason (cluster was down, the
controller was behind), how late is too late to bother starting it at
all?" Leaving it unset means "no deadline — start it whenever, no matter
how overdue." Pick a value that's generous relative to how often this
schedule fires, not an arbitrarily tiny number that would make the
CronJob skip runs under perfectly ordinary jitter.

Everything under `jobTemplate.spec` is exactly the Job fields you already
wrote in `job.yaml` — same container, same command shape, same
resources — just with `completions: 1` instead of `4` this time, since a
single scheduled tick processes one shard, not a batch of four.
