# Hint 2

`kubectl top pod` shows you *resident* memory (RSS-ish) right now, not
`MEM_MB`. The fixture app's `MEM_MB` knob allocates and holds that many
MiB in one `bytearray` -- but the Python interpreter itself, the
threading HTTP server, the stdlib, and normal process bookkeeping all
cost memory too, on top of that. So the number `kubectl top` reports for
`profile-me` will always read a bit *above* the raw `MEM_MB` value you
saw in the YAML -- that gap is real per-process overhead, not
measurement noise, and it's exactly why "I know `MEM_MB=180` so I'll set
`limits.memory: 180Mi`" is already wrong before you've run anything.

Once you have a real number from `kubectl top`, the question becomes
"how much margin above that measured number is enough." Zero margin means
any normal fluctuation (a slightly bigger response buffer, GC not having
run yet, a burst of concurrent requests) risks tipping you over your own
limit and getting OOMKilled by your *own* right-sizing choice -- which is
a real, valid way to fail this task, not a hypothetical edge case. Too
much margin runs into the policy cap from hint 1. There's a defensible
range between "just barely enough" and "wildly over," and it's narrow
enough that measuring first is the only way to reliably land in it.

The same logic applies to CPU: `CPU_BURN_THREADS=1` means one thread that
never stops spinning, which will happily consume as much CPU as you give
it. `kubectl top` will show you roughly how much of a core that one busy
thread actually costs on this cluster's nodes -- use that as your
starting point for `requests.cpu`, not a guess.
