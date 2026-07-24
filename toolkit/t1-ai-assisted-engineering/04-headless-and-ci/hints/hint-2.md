**The script.** Build the prompt as a shell variable from
`git diff "$BASE_REF"` (default `$BASE_REF` to `origin/main` if no
argument was given -- `"${1:-origin/main}"`), then pass it as the `-p`
argument. Add `--output-format json` and `--allowedTools "Read"` (this
script is read-only review, it never needs to edit anything or run
arbitrary commands). Guard the empty-diff case (nothing changed --> no
point calling the API) before you build the prompt.

**The workflow trigger.** GitHub Actions' `pull_request` trigger accepts
a `types:` list restricting which PR sub-events fire it --
`opened`, `synchronize`, `labeled`, etc. The list you want here is
exactly `[labeled]`. On its own, that still fires for ANY label anyone
applies -- add an `if:` condition on the job (or the specific step) that
checks `github.event.label.name` against the one label you actually care
about (e.g. `ai-review`), so applying an unrelated label like `bug`
doesn't trigger a review.

**The AI-review step.** You need the CLI available in the runner (a
`run:` step installing it, e.g. via npm) before you can call
`claude -p ...` in a later step -- or you can shell the two into one
`run:` block. Either way, the same headless contract from the script
applies here too: `-p`, `--output-format`, no interactive prompt.
