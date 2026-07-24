# Hint 1 — direction

`hyperfine` takes multiple commands as separate positional arguments and
benchmarks each in turn — you don't wrap them in a loop or run it twice.
The two commands need to actually answer the same question (same file
tree, same count) for the comparison to be meaningful at all; only the
*means of counting* should differ between them.
