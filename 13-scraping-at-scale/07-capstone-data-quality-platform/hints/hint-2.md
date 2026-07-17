Two specific traps, both of which show up as CP1/CP2 failures that are hard
to trace back to their cause if you don't know to look for them.

**The fingerprint payload shape decides whether nonce-stripping is a
guarantee or a habit.** If `changedetect.fingerprint()` hashes a raw
response body (or anything derived from one that still contains the nonce
field), you have to remember, forever, to strip that one field correctly
for every markup version AND the JSON endpoint, in every code path that
ever calls `fingerprint()`. If instead it hashes the dict
`pipeline.extract_fields()` already returns, the nonce is structurally
absent -- `extract_fields` never had a reason to extract it, since it isn't
one of the 7 fields the task ever asked for. Prefer the second shape; it
turns "did I remember to exclude the nonce" into "is nonce extraction even
possible," which is a much stronger guarantee, and it's exactly the kind of
design decision DESIGN.md's change-detection section asks you to defend.

**Metrics must survive being built more than once in the same process.**
CP1 calls `run_pipeline` once; CP2 calls it TWICE (day 0 and day 1, both
under chaos) in the same Python process. If `build_registry()`
unconditionally calls `Counter(...)`/`Gauge(...)`/`Histogram(...)` every
time it's invoked, the second call raises `prometheus_client`'s "Duplicated
timeseries in CollectorRegistry" error -- and that error will surface as a
confusing crash deep inside your SECOND `run_pipeline` call, not as an
obvious "you called this twice" message. Guard `build_registry()` so a
second call is a no-op that just returns the already-built registry
(a module-level flag, or checking whether the six metric objects are
already non-`None`, both work).
