Start by naming precisely what the naive `buffer = []` (or `asyncio.Queue()`
with no `maxsize`) is missing, because "just check the length before
appending" is not the right mental model.

An unbounded buffer's `append`/`put` never refuses. The producer can always
add one more item, regardless of how far behind the consumer is. So the only
way to keep it under a cap with that kind of buffer is for the producer to
watch the buffer's size itself and decide when to hold back -- something
like:

```python
while len(buffer) >= max_in_flight:
    await asyncio.sleep(0.01)
buffer.append(item)
```

This "works" in the sense that it eventually stays near the cap, but think
about what it's actually doing: burning CPU cycles re-checking a condition
on a timer, with no way to wake up the instant a slot actually frees --
only on the next tick of that sleep. Worse, there's a real gap between the
`while` check and the `append`: nothing stops two produced items from both
passing the check before either one appends, briefly blowing past the cap.
This is polling, not blocking, and polling is never the mechanism you want
when something else (the consumer) can tell you precisely when the
condition changes.

What you want instead is a buffer whose *own* "add to me" operation is the
thing that stalls -- synchronously, from the producer's point of view --
until the consumer has made room. No separate counter, no timer, no
re-checking. The producer calls one function; that function simply doesn't
return until there's space. Same idea for the consumer's "give me the next
item" -- it shouldn't return until there is one. What kind of standard
library primitive already has exactly this "block until the operation can
proceed" shape, in both directions?
