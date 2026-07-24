# Hint 3

Not a manifest to paste -- a walk-through of how to actually read
`leak-victim`'s death, since `NOTES.md` grades whether you got this right,
not just whether you ran a command.

**Do the arithmetic before you look at the clock.** `leak-victim` starts
with `requests.memory: 64Mi`, no `MEM_MB` set (so a small, mostly-fixed
interpreter baseline rather than a big deliberate hold), and
`limits.memory: 128Mi`. `LEAK_MB_PER_S=5` means resident memory grows by
roughly 5MiB every second, forever, starting from that baseline. Work out
roughly how many seconds it should take to cross from "baseline usage"
to "128MiB" at 5MiB/s -- that's your predicted time-to-death. Then run
`given/observe-oomkill.sh` and compare `finishedAt - startedAt` in its
output against your prediction. They should roughly agree; if your
predicted number and the observed number are wildly different, you've
misread one of the three numbers involved (baseline, rate, or limit).

**Read the container status fields, not just the pod phase.** `kubectl
get pod leak-victim -o yaml` (or the `observe-oomkill.sh` output) shows
you `status.containerStatuses[0].state.terminated` with `exitCode`,
`reason`, `startedAt`, `finishedAt`. `exitCode: 137` decomposes as
`128 + 9` -- 128 is the kernel's "died from a signal" offset, 9 is
`SIGKILL`'s number. That decomposition is worth writing out explicitly in
`NOTES.md`; "137" as a bare fact you memorized is a much weaker answer
than "137 because 128 + SIGKILL(9), meaning something sent this process
an unblockable kill signal it couldn't catch or clean up after."

**Don't trust `reason` blindly, but don't ignore it either.** As the
README says, this cluster's containerd/kubelet combination often reports
`reason: Error` for a container that kernel logs prove was genuinely
OOM-killed (`Memory cgroup out of memory: Killed process ...` in
`docker exec <node> dmesg`, if you want to go looking for it -- not
required, just available). Note in `NOTES.md` which signal you actually
relied on to conclude "this was an OOMKill" versus which signal you'd
normally expect to rely on in a cluster where the `reason` string is
accurate.

**The counterfactual question in `NOTES.md`** asks whether raising
`leak-victim`'s memory limit to something enormous would let it survive
indefinitely, or whether it's doomed no matter what limit you give it.
Think about what `LEAK_MB_PER_S` actually does over an unbounded time
horizon before you answer -- there's a real, defensible position here,
and it's not "it depends," it's a specific claim you can justify with the
rate/limit relationship you already worked out above.
