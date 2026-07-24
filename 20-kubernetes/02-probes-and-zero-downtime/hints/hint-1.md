# Hint 1

There are three separate questions being asked here, and the broken fixture
answers all three wrong. Don't try to fix them with one probe — figure out
which question each probe type is actually answering:

- "Has this container finished booting yet?" — nobody is asking this
  question at all right now. That's the missing piece that lets liveness
  kill a pod that's simply still starting up.
- "Is this pod currently able to serve a request?" — nobody is asking this
  either. That's why the Service happily routes traffic to a pod whose app
  hasn't bound its port.
- "Is this pod stuck/wedged and needs a hard restart?" — this is the only
  question being asked, and it's being asked way too early and way too
  aggressively for an app that takes 8 seconds to start.

Fix the missing questions before you retune the one that's already there.
Once you have a probe answering "has it finished booting," you can let the
other two probes assume the answer was "yes" before they start caring.

Separately: watch what `given/observe.sh` reports about restarts, not just
dropped requests. A slow-starting app being killed by liveness produces a
different signature than an app that won't die when asked to. You have both
problems in this fixture — the second one is about what happens at the
*end* of a pod's life, not the start, and it needs a different fix than the
probes.
