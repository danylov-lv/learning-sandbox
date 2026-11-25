Don't start by looking for "the bug." A postmortem that ends at a single
line of broken code is usually a postmortem that stopped one layer too
early -- in a real system, one broken thing rarely takes down an
unrelated service for four hours on its own. Something at each layer had
to respond to the layer below it in a way that made things worse, not
better, for this to have run this long.

Read `INCIDENT.md` at least twice before you write anything. The first
pass, just build the timeline in your head. The second pass, pay
attention to what did NOT trigger an alert, and ask why not -- a
monitoring rule that's watching the wrong thing is just as load-bearing
as a monitoring rule that fires correctly. Also pay attention to which
services are named in the evidence that you might not expect to be
related to each other at all.

There are at least four separate "layers" of decision-making visible in
the evidence -- something the target site did, something the retry
policy did in response, something the autoscaler did in response to
that, and something a shared piece of infrastructure did in response to
that. Each of those four is a place where a reasonable-sounding, locally
correct decision produced a bad global outcome. Find all four before you
try to write the single-sentence version of what happened.
