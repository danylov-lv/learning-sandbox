# Hint 1

Start with events, not `describe` — `describe` shows you the same events
but buried under a wall of spec you already know (you wrote the fixture,
or in a real incident you'd already have the manifest). The fast path:

```bash
kubectl -n t09 get events --sort-by=.lastTimestamp
```

Every one of these five pods generates a `FailedScheduling` event, and the
scheduler packs the actual reason into the event's message field — it
aggregates across all nodes it tried and tells you, per node, which
predicate rejected it. Read the whole message, not just the reason code;
"FailedScheduling" alone tells you nothing you don't already know from
`kubectl get pods` showing `Pending`.

If an event scrolled off or you want one pod's history in isolation:

```bash
kubectl -n t09 describe pod <name>
```

The `Events` section at the bottom is what you want; everything above it
is the spec you can already read from `given/zoo.yaml` — except you were
asked not to read that file yet, so this is genuinely your only window
into what each pod is asking for and why it can't get it.

One thing worth internalizing before you look closer: these five pods do
not all fail for the same reason wearing different clothes. If your
diagnosis for `pod-b` and `pod-c` come out reading identically, look
again — they're both scheduling-constraint failures, but they're not the
*same* constraint, and `DIAGNOSIS.md` is graded per pod, not as one
diagnosis copy-pasted five times.
