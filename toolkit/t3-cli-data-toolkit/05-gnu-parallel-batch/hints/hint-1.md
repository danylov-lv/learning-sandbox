# Hint 1 — direction

`parallel` fans one command template out across a list of inputs, running
several instances at once instead of one at a time. Write the per-file
command first and get it working correctly on a *single* input file
(redirected to a throwaway output) before you wire it into `parallel` at
all — debugging a transform and debugging parallelism at the same time is
harder than it needs to be.
