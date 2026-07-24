A Claude Code hook is just a command Claude Code runs and feeds JSON to
on stdin. Nothing about it requires the `claude` binary to be involved at
all while you're developing and testing it -- you can invoke your own
hook script directly, feed it JSON by hand, and see what it does. That's
exactly how the validator checks your work: it never launches `claude`,
it launches your script.

Both scripts here have the same three-step shape: read the JSON payload,
run a command against the project, report the result in a way Claude
Code understands. Focus on getting that report-back format exactly right
-- an otherwise-correct hook that reports failure the wrong way is
indistinguishable, to the grading harness, from a hook that doesn't check
anything at all.

Re-read the two module-16-style gotchas already spelled out in each
script's docstring before you write a line of subprocess code -- they are
there because they're easy to get wrong on Windows specifically, and
getting them wrong produces a hook that looks like it's working
(non-crashing) while actually testing nothing.
