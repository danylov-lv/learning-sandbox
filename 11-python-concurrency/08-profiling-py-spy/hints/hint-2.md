A flamegraph's x-axis is samples, not a timeline -- it does not tell you
"this ran, then that ran." What it does tell you is *proportion*: the wider
a frame, the larger the share of all samples that were captured with that
frame on the stack. Stack depth is the y-axis -- a frame's children sit
above it, narrower, showing what fraction of its own width was spent inside
each callee.

The frame you're looking for is wide **and** near the top (a leaf, or close
to it) -- that combination means the process was actually executing inside
that function itself for a large share of samples, not just passing through
it on the way to something else. A wide frame low in the stack with an
equally wide child above it is just a call path everything happens to go
through; keep following the width upward until it either narrows sharply
(you've passed the hot part) or stays wide all the way to a leaf (that leaf
is your answer).

If you're using `py-spy dump` instead: it has no width to compare, but
running it several times and looking at what's consistently sitting at the
very top of the stack (the innermost frame, listed first) is doing the same
job by hand -- a sampling profiler one sample at a time. A function that
shows up there in most of your dumps, while the app is supposedly juggling
many concurrent things, is not a coincidence.

One more thing worth noticing once you've found the frame: check what's
*missing* around it in the stack -- specifically, whether there's an
`await` anywhere between the event loop's own scheduling frames and your
hot frame. If there isn't, that's the mechanism, not just the symptom.
