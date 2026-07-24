`claude -p "<prompt>"` runs one turn non-interactively and exits -- that's
the entire mechanism headless mode is. Everything else in this task is
about building a good, self-contained prompt (from `git diff`, not from
asking a human to paste something) and controlling what the call is
allowed to do and how its result comes back (`--output-format`,
`--allowedTools`).

For the workflow: the requirement is specifically that this step runs
when someone applies a label to a PR, not on every push and not on every
PR update. Look at what GitHub Actions trigger shape distinguishes
"a PR was opened/updated" from "a specific label was added to a PR" --
they're both under the `pull_request` trigger, but one extra key changes
which events fire it.

A label-triggered `if:` you'll want twice: once so the WORKFLOW doesn't
even start for irrelevant labels event types you didn't ask for, and
separately so the job/step doesn't run for every OTHER label someone
might apply to the same PR.
